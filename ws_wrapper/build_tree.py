#!/usr/bin/env python3
from ws_wrapper.exceptions import HttpResponseError
from ws_wrapper.util import convert_arg_to_ott_int
from peyutil import (is_str_type,
                     read_as_json,
                     write_as_json)
from threading import RLock, Thread
import logging
import tempfile
from queue import Queue
import json
import re
import os
import time
import subprocess

log = logging.getLogger('ws_wrapper')

################################################################################
# ws_wrapper_INI = the settings dict created from an INI file when ws_wrappers
#       Pyramids app is launched.
# scratch = abspath to value of ws_wrapper_INI["propinquity.scratch_dir"]
# propinq = path specified by ws_wrapper_INI["propinquity.propinquity_dir"]
# pr is the instance of the PropinquityRunner
#
# working directory structure:
#   propinq/checkpoint_then_check.bash = bash script launched by each wrapper; each
#           wrapper invokes this with its own arguments (snakemake config) and
#           results directory.
#   scratch/wrappers  = pr.wrappers_par
#   scratch/wrappers/uid = wrapper_dir
#   scratch/wrappers/uid/exit-code.txt = pr.get_exit_code_fp(uid). Exists on exit.
#   scratch/wrappers/uid/exec_custom_synth.bash pr._get_launcher_fp(uid) (this is the
#           ... script that calls propinq/checkpoint_then_check.bash)
#   scratch/results = pr.results_par
#   scratch/results/uid/ (contents of propinquity output


def wait_for_file_to_exist(fp, sleep_seconds):
    """Sleeps `sleep_seconds` at a while checking for `fp` to exist."""
    while True:
        if os.path.exists(fp):
            return True
        time.sleep(sleep_seconds)

def synth_launch_worker(prop_runner, sleep_seconds):
    """Infinite loop calling for launching synth based on uid from prop_runner.get()

    `sleep_seconds` is the duration of sleep between checks for the existence
    of the file that flags the exit of the synth process (pr.get_exit_code_fp(uid))."""
    log.debug('Launching synth_launch_worker thread')
    q = prop_runner.queue
    while True:
        uid = q.get()
        log.debug('Launching custom_synth {uid}'.format(uid=uid))
        prop_runner.do_launch(uid)
        exit_fp = prop_runner.get_exit_code_fp(uid)
        wait_for_file_to_exist(exit_fp, sleep_seconds)
        log.debug('custom_synth {uid} finished'.format(uid=uid))
        try:
            prop_runner.flag_as_exited(uid)
        except:
            pass
        q.task_done()


class PropinquityRunner(object):
    """Class for coordinating on-demand runs of propinquity"""
    status_json = 'run_status.json'
    _launcher_fn = "exec_custom_synth.bash"
    _exit_code_fn = 'exit-code.txt'
    _download_attr = 'download_url'

    def __init__(self, settings_dict):
        """Creates (a presumably singleton), and launches a thread for spawning jobs.

        settings_dict['propinquity.scratch_dir'] => scratch_dir
        settings_dict['propinquity.propinquity_dir'] => working directory of snakemake
            call (the "checkpoint_then_check.bash" in this dir is run).
        settings_dict['propinquity.init_config_json'] => path to JSON file
            with the properties of the snakemake configuration that are
            common to all runs. Currently, this is:
            1. "opentree_home" (if you have single directory (the opentree_home) that holds:
                the git-controlled inputs to synthesis:
                    A. opentree_home/phylesystem/shards/phylesystem-1
                    B. opentree_home/phylesystem/shards/collections-1
                    C. opentree_home/script-managed-trees
            2. "ott_dir" which is the directory of the extinct-flagged OTT
        settings_dict['propinquity.propinquity_env'] => optional file path
            for a file to be sourced by each bash script before it runs snakemake.
            Can be empty if the otcetera-based tools (and other propinquity
            prerequisites) are on the PATH of the process that is running ws_wrapper.
        settings_dict['propinquity.sleep_seconds'] controls how long the
            wrapper script waits between checks for the existence of the file
            that indicates that the synth run is completed. (longer yields more
            latency, too tiny could result in lots of CPU spent waking and checking
            for a file on a long running process). Default is 30

        """
        self.top_scratch_dir = settings_dict.get('propinquity.scratch_dir')
        if self.top_scratch_dir is None:
            self._raise_missing_setting('propinquity.scratch_dir')
        self.top_scratch_dir = os.path.abspath(self.top_scratch_dir)
        if not os.path.exists(self.top_scratch_dir):
            try:
                os.makedirs(self.top_scratch_dir)
            except:
                self._raise_misconfigured('propinquity.scratch_dir', 'Could not create scratch dir.')
        elif not os.path.isdir(self.top_scratch_dir):
            self._raise_misconfigured('propinquity.scratch_dir', 'Path for scratch dir is not a directory.')
        self.wrappers_par = os.path.join(self.top_scratch_dir, 'wrappers')
        if not os.path.exists(self.wrappers_par):
            os.makedirs(self.wrappers_par)
        self.results_par = os.path.join(self.top_scratch_dir, 'results')
        self.propinq_root = settings_dict.get('propinquity.propinquity_dir')
        if self.propinq_root is None:
            self._raise_missing_setting('propinquity.propinquity_dir')
        self.propinq_root = os.path.abspath(self.propinq_root)
        if not os.path.isdir(self.propinq_root):
            self._raise_misconfigured('propinquity.propinquity_dir', 'Directory not found.')
        snakemake_driver = os.path.join(self.propinq_root, "checkpoint_then_check.bash")
        if not os.path.isfile(snakemake_driver):
            self._raise_misconfigured('propinquity.propinquity_dir', '{} not found.'.format(snakemake_driver))

        self.init_config_fp = settings_dict.get('propinquity.init_config_json')
        if self.init_config_fp is None:
            self._raise_missing_setting('propinquity.init_config_json')
        if not os.path.isfile(self.init_config_fp):
            self._raise_misconfigured('propinquity.init_config_json', 'File not found.')
        try:
            self.init_config = read_as_json(self.init_config_fp)
        except:
            self._raise_misconfigured('propinquity.init_config_json', 'filepath not parseable as JSON')
        if not isinstance(self.init_config, dict):
            self._raise_misconfigured('propinquity.init_config_json', 'filepath does not hold a JSON dict')
        self.propinquity_env = settings_dict.get('propinquity.propinquity_env', '')
        if self.propinquity_env:
            if not os.path.isfile(self.propinquity_env):
                self._raise_misconfigured('propinquity.propinquity_env', 'Directory not found.')
        else:
            self.propinquity_env = ''
        self.sleep_seconds = settings_dict.get('propinquity.sleep_seconds')
        try:
            self.sleep_seconds = float(self.sleep_seconds)
        except:
            if self.sleep_seconds is not None:
                m = '"{}" is not a number'.format(self.sleep_seconds)
                self._raise_misconfigured('propinquity.sleep_seconds', m)
            self.sleep_seconds = 30
        self.queue_order_number = 0
        self.run_queue_lock = RLock()
        self.completed = set()
        self.running = set()
        self.erred = set()
        self.queue = Queue()
        self.queue_ids = set()
        self.known_runs_lock = RLock()
        self.known_runs_dict = {}

        def worker_for_pr():
            synth_launch_worker(prop_runner=self, sleep_seconds=self.sleep_seconds)
        Thread(target=worker_for_pr, daemon=True).start()
        # This will trigger the indexing of existing synth runs that
        #   where finished by previous ws_wrapper runs.
        self.get_runs_by_id(queue_if_needed=True)

    def get_exit_code_fp(self, uid):
        return os.path.join(self.get_wrapper_dir(uid), PropinquityRunner._exit_code_fn)

    def do_launch(self, uid):
        self._add_discard_from_locked_sets(uid, self.running, self.queue_ids, 'do_launch')
        launcher = self._get_launcher_fp(uid)
        pid = subprocess.Popen(["/bin/bash", launcher]).pid
        logging.debug('Launched custom synth {uid} with pid={pid}'.format(uid=uid, pid=pid))
        blob = None
        try:
            blob = self._set_status_blob_attr(uid, "status", "RUNNING")[1]
        finally:
            if blob is not None:
                self._update_key_in_mem_status_dicts(uid, blob)
        pidfile = os.path.join(self.get_wrapper_dir(uid), 'pid.txt')
        try:
            with open(pidfile, 'w') as pout:
                pout.write('{}\n'.format(pid))
        except:
            logging.warning('Error writing to {}'.format(pidfile))
            pass
        return pid

    def flag_as_exited(self, uid):
        self._add_discard_from_locked_sets(uid, self.completed, self.running, 'flag_as_exited')
        self.attempt_set_exit_code_from_ec_file(uid=uid)

    def get_status_blob(self, uid):
        """Returns a status dict for uid, the status will be UNKNOWN if the JSON status file
        was not found.
        """
        r = self._read_status_blob(uid)
        if r is None:
            r = {}
        if not r:
            r["synth_id"] = uid
            r["status"] = "UNKNOWN"
        return r

    def attempt_set_exit_code_from_ec_file(self, uid, blob=None):
        ecfp = self.get_exit_code_fp(uid)
        if os.path.exists(ecfp):
            try:
                ec_content = int(open(ecfp, 'r').read().strip())
            except:
                log.warning("{} did not contain an integer".format(ecfp))
                pass
            else:
                blob = self._write_exit_code_to_status_json(uid, ec_content, blob=blob)
        return blob

    def get_archive_filepath(self, request, uid, ext='tar.gz'):
        if ext not in ['tar.gz']:
            m = 'Archive type "{}" not currently supported'.format(ext)
            raise HttpResponseError(m, 404)
        with self.known_runs_lock:
            status_blob = self.known_runs_dict.get(uid)
        if status_blob is None:
            self.get_runs_by_id()
            with self.known_runs_lock:
                status_blob = self.known_runs_dict.get(uid)
            if status_blob is None:
                raise KeyError('run id = "{}" not known'.format(uid))
        status_blob = self.add_download_url_if_needed(status_blob, request)
        redirect_uid = status_blob.get("redirect")
        if redirect_uid is not None:
            return self.get_archive_filepath(request, redirect_uid, ext=ext)
        return self._get_validated_archive_filepath(uid, ext=ext)

    def get_runs_by_id(self, queue_if_needed=False):
        """Updates the in-memory fields that keep track of jobs.
        Returns a copy of self.known_runs_dict.

        Can update: self.known_runs_lock, self.queue_order_number,
          self.completed, self.erred.add(el[1])

        If `queue_if_needed` is True, then _add_to_run_queue may be called.
        This should only be done by the __init__ method to queue jobs that
            were written by a previous instance of the server, but were
            never executed.
        """
        completed, running, to_queue, erred = [], [], [], []
        wpar = self.wrappers_par
        subdir_list = os.listdir(wpar)
        with self.known_runs_lock:
            ret_dict = dict(self.known_runs_dict)
        new_entries = {}
        with self.run_queue_lock:
            qon = self.queue_order_number
        for sd in subdir_list:
            if sd in ret_dict:
                continue
            j = self._read_status_blob(uid=sd)
            if not j:
                continue
            jqon = j.get("queue_order", qon)
            try:
                jqon = int(jqon)
                if jqon > qon:
                    qon = jqon
            except:
                pass
            uid = j["synth_id"]
            exit_code = j.get('exit_code')
            if exit_code is None:
                j = self.attempt_set_exit_code_from_ec_file(uid=uid, blob=j)
                exit_code = j.get('exit_code')
            el = (jqon if jqon is not None else -1, uid, j)
            if exit_code is not None:
                if exit_code == 0:
                    completed.append(el)
                else:
                    erred.append(el)
            else:
                fp = os.path.join(wpar, sd)
                if os.path.exists(os.path.join(fp, "running.txt")):
                    running.append(el)
                else:
                    to_queue.append(el)
            new_entries[uid] = j
        if not new_entries:
            return ret_dict
        # We have found some run artifacts that are not in the known_runs_dict
        with self.known_runs_lock:
            self.known_runs_dict.update(new_entries)
        ret_dict.update(new_entries)
        completed.sort()
        running.sort()
        for el in to_queue:
            if el[0] == -1:
                qon += 1
                # noinspection PyUnresolvedReferences
                el[0] = qon
        to_queue.sort()
        erred.sort()
        no_longer_running = completed + erred
        log.debug('getting run_queue_lock in scan_scratch_dir_for_run_state')
        with self.run_queue_lock:
            if qon > self.queue_order_number:
                self.queue_order_number = 1 + qon
            for el in completed:
                self.completed.add(el[1])
            for el in erred:
                self.erred.add(el[1])
            for el in running:
                self.running.add(el[1])
            for el in no_longer_running:
                if el[1] in self.running:
                    self.running.remove(el[1])
        log.debug('released run_queue_lock in scan_scratch_dir_for_run_state')
        if queue_if_needed:
            for el in to_queue:
                self._add_to_run_queue(el[1], queue_order=el[0], stat_blob=el[2])
        return ret_dict

    def trigger_synth_run(self,
                          coll_owner,
                          coll_name,
                          root_ott_int,
                          user_initiating_run=None):
        return trigger_synth_run(self,
                                 coll_owner,
                                 coll_name,
                                 root_ott_int,
                                 user_initiating_run=user_initiating_run)

    def gen_uniq_tuple(self, coll_owner, coll_name, root_ott_int):
        """Returns a uniq wrapper_dir, results_dir, and uid for a new
        job (coll_owner/coll_name collection and root_ott as an integer)."""
        wd = self.wrappers_par
        rp = self.results_par
        if isinstance(coll_owner, tuple) or isinstance(coll_owner, list):
            pref = '_'.join([str(i) for i in ('multi', coll_owner[0], coll_name[0], root_ott_int, 'tmp')])
        else:
            pref = '_'.join([str(i) for i in (coll_owner, coll_name, root_ott_int, 'tmp')])
        n = 0
        while True:
            wuid = tempfile.mkdtemp(prefix=pref, dir=wd)
            uid = os.path.split(wuid)[-1]
            res_d = os.path.join(rp, uid)
            if not os.path.exists(res_d):
                return wuid, res_d, uid
            n += 1
            if n > 10:
                m = "Could not create directory for custom synthesis after multiple attempts."
                raise HttpResponseError(m, 500)
            m = "Filepath {} already exists, generating a new uniq_dir pair"
            log.warning(m.format(res_d))

    def get_wrapper_dir(self, uid):
        return os.path.join(self.wrappers_par, uid)

    def _raise_missing_setting(self, variable):
        msg = 'This instance of the web server was not configured correctly ' \
              'to support the launching of custom synthesis jobs. The ' \
              'config file lacks a {variable} setting.'
        raise HttpResponseError(msg.format(variable=variable), 501)

    def _raise_misconfigured(self, variable, err):
        msg = 'This instance of the web server was not configured correctly ' \
              'to support the launching of custom synthesis jobs. When ' \
              'checking the {variable} setting, an ' \
              'error was encountered: {err}'
        msg = msg.format(variable=variable, err=err)
        raise HttpResponseError(msg, 501)

    def _next_queue_order(self):
        log.debug('getting lock in _next_queue_order')
        with self.run_queue_lock:
            self.queue_order_number += 1
            x = self.queue_order_number
        log.debug('released lock in _next_queue_order')
        return x

    def _add_to_run_queue(self, uid, queue_order=None, stat_blob=None):
        if stat_blob is None:
            stat_blob = {"synth_id": uid, }
        if queue_order is None:
            queue_order = stat_blob.get('queue_order')
            if queue_order is None:
                queue_order = self._next_queue_order()
                stat_blob["queue_order"] = queue_order
        log.debug('getting lock in _add_to_run_queue')
        with self.run_queue_lock:
            self.queue_ids.add(uid)
            self.queue.put_nowait(uid)
        log.debug('released lock in _add_to_run_queue')
        try:
            self._set_status_blob_attr(uid, "status", "QUEUED", blob=stat_blob)
        finally:
            self._update_key_in_mem_status_dicts(uid, stat_blob)
        return stat_blob


    def _update_key_in_mem_status_dicts(self, uid, blob):
        with self.known_runs_lock:
            self.known_runs_dict[uid] = blob


    def set_status_blob_attr(self, uid, key, value, blob):
        self._set_status_blob_attr(uid, key, value, blob)
        self._update_key_in_mem_status_dicts(uid, blob)
        return blob

    def add_download_url_if_needed(self, status_blob, request):
        download_attr = PropinquityRunner._download_attr
        run_stat = status_blob.get("status", "")
        if run_stat == "COMPLETED" or run_stat == "FAILED":
            if download_attr not in status_blob:
                uid = status_blob["synth_id"]
                if self.check_for_redirect(uid, status_blob, request):
                    return status_blob
                r_u = request.route_url('tol:custom-built-tree',
                                        build_id=uid,
                                        ext="tar.gz")
                return self.set_status_blob_attr(uid, download_attr, r_u, status_blob)
        return status_blob

    def check_for_redirect(self, uid, status_blob, request):
        download_attr = PropinquityRunner._download_attr
        redirect_file = os.path.join(self.results_par, uid, "REDIRECT.txt")
        if os.path.exists(redirect_file):
            new_id_fp = open(redirect_file, "r").read().strip()
            if os.path.isdir(new_id_fp):
                new_id = os.path.split(new_id_fp)[1]
                new_stat_blob = self._read_status_blob(new_id)
                if not new_stat_blob:
                    log.warning("Redirection from {} to {} failed".format(uid, new_id))
                    return status_blob
                self.add_download_url_if_needed(new_stat_blob, request)
                dr = new_stat_blob.get(download_attr)
                if dr is not None:
                    self._set_status_blob_attr(uid, download_attr, dr, status_blob)
                self._set_status_blob_attr(uid, "redirect", new_id, status_blob)
                self.set_status_blob_attr(uid, "status", "REDIRECTED", status_blob)
            else:
                log.warning("Redirection from {} to non-existing {}".format(uid, new_id_fp))
            return True
        return False

    def _set_status_blob_attr(self, uid, key, value, blob=None):
        """Sets a key value pair in the status JSON file.
        `blob` can be the current version of the content of that file,
            if the caller is confident that this it is up-to-date.
        Returns (was_altered, blob)"""
        if blob is None:
            blob = self._read_status_blob(uid)
        unaltered = blob.get(key) == value
        if value is None:
            if key in blob:
                del blob[key]
        else:
            blob[key] = value
        self._write_status_blob(uid, blob)
        return not unaltered, blob

    def _write_exit_code_to_status_json(self, uid, exit_code, blob=None):
        if blob is None:
            blob = self.get_status_blob(uid)
        try:
            self._set_status_blob_attr(uid, "exit_code", exit_code, blob=blob)
            blob["exit_code"] = exit_code
            if exit_code == 0:
                self._set_status_blob_attr(uid, "status", "COMPLETED", blob=blob)
            elif exit_code is not None:
                self._set_status_blob_attr(uid, "status", "FAILED", blob=blob)
        finally:
            self._update_key_in_mem_status_dicts(uid, blob)
        return blob


    def _write_status_blob(self, uid, blob):
        run_status_json = self._get_status_fp(uid)
        par = os.path.split(run_status_json)[0]
        hidden = tempfile.mkstemp(dir=par, prefix='status_json_')[1]
        try:
            with open(hidden, 'w', encoding='utf-8') as outp:
                json.dump(blob, outp)
            os.rename(hidden, run_status_json)
        except:
            if os.path.exists(hidden):
                os.remove(hidden)
            raise

    def _get_launcher_fp(self, uid):
        pd = self.get_wrapper_dir(uid)
        return os.path.join(pd, PropinquityRunner._launcher_fn)

    def _get_status_fp(self, uid):
        par_dir = self.get_wrapper_dir(uid)
        return os.path.join(par_dir, PropinquityRunner.status_json)

    def _add_discard_from_locked_sets(self, uid, to_add=None, to_discard=None, tag=None):
        """Helper for adding, discarding from sets under run_queue_lock"""
        if to_add is None and to_discard is None:
            return
        if tag:
            log.debug('getting lock in {}'.format(tag))
        with self.run_queue_lock:
            try:
                self.queue_ids.discard(uid)
            except:
                pass
            try:
                self.running.add(uid)
            except:
                pass
        if tag:
            log.debug('released lock in {}'.format(tag))

    def _read_status_blob(self, uid):
        """Reads the status JSON for uid, if it exists.
        Returns the blob, None if the file is absent, an empty dict if not parseable.
        """
        sj = self._get_status_fp(uid)
        if not os.path.isfile(sj):
            return None
        try:
            return read_as_json(sj)
        except:
            log.warning("Could not read {} as JSON".format(sj))
            return {}

    def _get_validated_archive_filepath(self, uid, ext):
        # See archive creation in _SYNTH_SHELL_TEMPLATE
        arch_fn = "{}.{}".format(uid, ext)
        return os.path.join(self.get_wrapper_dir(uid), arch_fn)


# Important to keep this restrictive to be Filename legal! see gen_uid
_COLL_NAME_RE = re.compile('^([-a-zA-Z0-9]+)/([-a-zA-Z0-9]+)$')

def _split_and_validate_coll_name(collection_name):
    try:
        m = _COLL_NAME_RE.match(collection_name)
        assert m
    except:
        m = 'Expecting a "input_collection" to have the form "owner_name/collection_name".'
        ' "{}" did not match this form. Either it is incorrectly formed or our regex for '
        'recognizing collections names (in ws_wrapper) is too strict.'
        raise HttpResponseError(m.format(collection_name), 400)
    else:
        coll_owner, coll_name = m.groups()
        return coll_owner, coll_name

def validate_custom_synth_args(collection_name, root_id):
    if collection_name is None:
        raise HttpResponseError('Expecting a "input_collection" parameter.', 400)
    coll_owner, coll_name = None, None
    if is_str_type(collection_name):
        coll_owner, coll_name = _split_and_validate_coll_name(collection_name)
    else:
        coll_owner, coll_name = [], []
        for el in collection_name:
            co, cn = _split_and_validate_coll_name(el)
            coll_owner.append(co), coll_name.append(cn)
    if root_id is None:
        raise HttpResponseError('Expecting a "root_id" parameter.', 400)
    ott_int = convert_arg_to_ott_int(root_id)
    if ott_int is None:
        raise HttpResponseError('Expecting a "root_id" parameter to be and integer or "ott#"', 400)
    return coll_owner, coll_name, ott_int


def trigger_synth_run(propinquity_runner,
                      coll_owner,
                      coll_name,
                      root_ott_int,
                      user_initiating_run=None):
    pr = propinquity_runner
    wrapper_par, results_dir, uid = pr.gen_uniq_tuple(coll_owner, coll_name, root_ott_int)

    snakemake_config = dict(pr.init_config)
    snakemake_config["root_ott_id"] = str(root_ott_int)
    snakemake_config["synth_id"] = uid
    if is_str_type(coll_owner):
        inp_coll = "{o}/{n}".format(o=coll_owner, n=coll_name)
    else:
        ic_list = ["{o}/{n}".format(o=o, n=n) for o, n in zip(coll_owner, coll_name)]
        inp_coll = ','.join(ic_list)
    snakemake_config["collections"] = inp_coll
    snakemake_config["cleaning_flags"] = "major_rank_conflict,major_rank_conflict_inherited,environmental,viral,barren,not_otu,hidden,was_container,inconsistent,hybrid,merged"
    snakemake_config["additional_regrafting_flags"] = "extinct_inherited,extinct"

    sm_cfg_fp = os.path.join(wrapper_par, 'config.json')
    write_as_json(snakemake_config, sm_cfg_fp)
    results_par = os.path.split(results_dir)[0]

    x = _SYNTH_SHELL_TEMPLATE.format(otttag="3.2",
                                     propinq_root=pr.propinq_root,
                                     sm_cfg_fp=sm_cfg_fp,
                                     results_par=results_par,
                                     par_dir=wrapper_par,
                                     uid=uid,
                                     propinquity_env=pr.propinquity_env)

    bfn = "custom_{uid}.bash".format(uid=uid)
    pbfp = os.path.join(wrapper_par, bfn)
    with open(pbfp, 'w', encoding='utf-8') as outf:
        outf.write(x)
    mv_and_exe_sh = pr._get_launcher_fp(uid)
    with open(mv_and_exe_sh, 'w', encoding='utf-8') as outf:
        outf.write(_MV_AND_EXE_TEMPLATE.format(par_dir=wrapper_par,
                                               bash_script=bfn))
    stat_blob = dict(snakemake_config)
    if user_initiating_run is not None:
        stat_blob["username_supplied"] = user_initiating_run
    return pr._add_to_run_queue(uid, stat_blob=stat_blob)


_MV_AND_EXE_TEMPLATE = """#!/bin/bash

if test -f "{par_dir}/exit-code.txt" ; then
    rm "{par_dir}/exit-code.txt" || exit
fi

function clean_up_running {{
    if test -f "{par_dir}/running.txt" ; then
        rm "{par_dir}/running.txt"
    fi
}}

# Write PID of this bash shell to file
echo $$ > "{par_dir}/running.txt" || exit 1

if ! cd "{par_dir}" ; then
    echo 2 > "{par_dir}/exit-code.txt"
    clean_up_running
    exit 1
fi
if ! bash "{bash_script}" >"{par_dir}/propinq-out.txt" 2>&1 ; then
    echo 1 > "{par_dir}/exit-code.txt"
    clean_up_running
    exit 1
fi

echo 0 > "{par_dir}/exit-code.txt"
clean_up_running
"""

_SYNTH_SHELL_TEMPLATE = """#!/bin/sh
set -x
export propenv="{propinquity_env}"
if ! test -z $propenv ; then
    if test -f "$propenv" ; then
        source "$propenv" || exit
    else
        echo "$propenv" does not exist
        exit 1
    fi
fi

if ! cd "{propinq_root}" ; then 
    echo cd to {propinq_root} failed
    exit 1
fi

if ! "./checkpoint_then_check.bash" "{sm_cfg_fp}" "{results_par}" "{uid}" ; then
    echo "propinquinty run failed"
    exit 1
fi

if ! cd "{results_par}" ; then
    echo "cd to {results_par} failed"
    exit 1
fi
if ! tar cfvz "in_progress_{uid}.tar.gz" "{uid}" ; then
    echo "tar failed"
    exit 1
fi
if ! mv "in_progress_{uid}.tar.gz" "{par_dir}/{uid}.tar.gz" ; then
    echo "mv of tar failed"
    exit 1
fi

"""