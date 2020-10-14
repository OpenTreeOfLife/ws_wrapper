#!/usr/bin/env python3
from ws_wrapper.exceptions import HttpResponseError
from ws_wrapper.util import convert_arg_to_ott_int
from peyotl.utility.str_util import is_str_type
from threading import RLock, Thread
# import hashlib
import logging
from queue import Queue
import json
import re
import os
import time
import subprocess

log = logging.getLogger('ws_wrapper')


def synth_launch_worker(prop_runner, sleep_seconds):
    log.debug('Launching synth_launch_worker thread')
    q = prop_runner.queue
    while True:
        uid = q.get()
        log.debug('Launching custom_synth {uid}'.format(uid=uid))
        prop_runner.do_launch(uid)
        pd = prop_runner.get_par_dir(uid)
        exit_fp = os.path.join(pd, 'exit-code.txt')
        while True:
            if os.path.exists(exit_fp):
                break
            time.sleep(sleep_seconds)
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

    def do_launch(self, uid):

        log.debug('getting lock in do_launch')
        with self.run_queue_lock:
            try:
                self.queue_ids.discard(uid)
            except:
                pass
            try:
                self.running.add(uid)
            except:
                pass
        log.debug('released lock in do_launch')
        launcher = self.get_full_path_to_launcher(uid)
        pid = subprocess.Popen(["/bin/bash", launcher]).pid
        logging.debug('Launched custom synth {uid} with pid={pid}'.format(uid=uid,
                                                                          pid=pid))
        d = self.read_status_json(uid)
        d["status"] = "RUNNING"
        self._write_status_blob(uid, d)
        return pid

    def flag_as_exited(self, uid):
        log.debug('getting lock in flag_as_exited')
        with self.run_queue_lock:
            try:
                self.running.discard(uid)
            except:
                pass
            try:
                self.completed.add(uid)
            except:
                pass
        log.debug('released lock in flag_as_exited')
        d = self.read_status_json(uid)
        fp = self.get_par_dir(uid)
        self.attempt_set_exit_code_from_ec_file(build_dir=fp, blob=d)

    def __init__(self, settings_dict):
        self.top_scratch_dir = settings_dict.get('propinquity.scratch_dir')
        if self.top_scratch_dir is None:
            self._raise_missing_setting('propinquity.scratch_dir')
        if not os.path.exists(self.top_scratch_dir):
            try:
                os.makedirs(self.top_scratch_dir)
            except:
                self._raise_misconfigured('propinquity.scratch_dir', 'Could not create scratch dir.')
        elif not os.path.isdir(self.top_scratch_dir):
            self._raise_misconfigured('propinquity.scratch_dir', 'Path for scratch dir is not a directory.')

        self.propinq_root = settings_dict.get('propinquity.propinquity_dir')
        if self.propinq_root is None:
            self._raise_missing_setting('propinquity.propinquity_dir')
        if not os.path.isdir(self.propinq_root):
            self._raise_misconfigured('propinquity.propinquity_dir', 'Directory not found.')

        self.ott_dir = settings_dict.get('propinquity.ott_dir')
        if self.ott_dir is None:
            self._raise_missing_setting('propinquity.ott_dir')
        if not os.path.isdir(self.ott_dir):
            self._raise_misconfigured('propinquity.ott_dir', 'Directory not found.')

        self.propinq_ini_fp = settings_dict.get('propinquity.base_ini_file')
        if self.propinq_ini_fp is None:
            self._raise_missing_setting('propinquity.base_ini_file')
        if not os.path.isfile(self.propinq_ini_fp):
            self._raise_misconfigured('propinquity.base_ini_file', 'File not found.')

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
        self.scan_scratch_dir_for_run_state()
        def worker_for_pr():
            synth_launch_worker(prop_runner=self, sleep_seconds=self.sleep_seconds)
        Thread(target=worker_for_pr, daemon=True).start()


    def _read_status_blob(self, directory):
        sj = os.path.join(directory, PropinquityRunner.status_json)
        try:
            return json.load(open(sj, 'r', encoding='utf-8'))
        except:
            return {}

    def attempt_set_exit_code_from_ec_file(self, build_dir, blob):
        uid = blob["id"]
        ecfp = os.path.join(build_dir, "exit-code.txt")
        if os.path.exists(ecfp):
            try:
                ec_content = int(open(ecfp, 'r').read().strip())
            except:
                pass
            else:
                self._write_exit_code_to_status_json(uid, ec_content, blob=blob)

    def scan_scratch_dir_for_run_state(self):
        completed, running, to_queue, erred = [], [], [], []
        subdir_list = os.listdir(self.top_scratch_dir)
        for sd in subdir_list:
            fp = os.path.join(self.top_scratch_dir, sd)
            j = self._read_status_blob(directory=fp)
            if j:
                qon = self.queue_order_number
                qon = j.get("queue_order", qon)
                try:
                    qon = int(qon)
                except:
                    qon = self.queue_order_number
                if qon > self.queue_order_number:
                    self.queue_order_number = 1 + qon
                uid = j["id"]
                exit_code = j.get('exit_code')
                if exit_code is None:
                    self.attempt_set_exit_code_from_ec_file(build_dir=fp, blob=j)
                el = (qon, uid)
                if exit_code is not None:
                    if exit_code == 0:
                        completed.append(el)
                    else:
                        erred.append(el)
                else:
                    if os.path.exists(os.path.join(fp, "running.txt")):
                        running.append(el)
                    else:
                        to_queue.append(el)
        completed.sort()
        running.sort()
        to_queue.sort()
        log.debug('getting lock in scan_scratch_dir_for_run_state')
        with self.run_queue_lock:
            for el in completed:
                self.completed.add(el[1])
            for el in running:
                self.running.add(el[1])
            for el in to_queue:
                self.queue.put_nowait(el[1])
                self.queue_ids.add(el[1])
        log.debug('released lock in scan_scratch_dir_for_run_state')

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

    def trigger_synth_run(self, coll_owner, coll_name, root_ott_int):
        return trigger_synth_run(self, coll_owner, coll_name, root_ott_int)

    def gen_uid(self, coll_owner, coll_name, root_ott_int):
        # hasher = hashlib.sha256()
        # hasher.update(bytes(repr((coll_owner, coll_name, root_ott_int)), encoding='utf-8'))
        # uid = hasher.hexdigest()
        return '_'.join([str(i) for i in (coll_owner, coll_name, root_ott_int)])

    def get_archive_filepath(self, uid):
        par = self.get_par_dir(uid)
        fn = 'custom_{}.tar.gz'.format(uid)
        return os.path.join(par, fn)

    def next_queue_order(self):
        log.debug('getting lock in next_queue_order')
        with self.run_queue_lock:
            self.queue_order_number += 1
            x = self.queue_order_number
        log.debug('released lock in next_queue_order')
        return x

    def add_to_run_queue(self, uid):
        d = {"id": uid,
             "status": "QUEUED",
             "queue_order": self.next_queue_order()
             }
        self._write_status_blob(uid, d)

        log.debug('getting lock in add_to_run_queue')
        with self.run_queue_lock:
            self.queue_ids.add(uid)
            self.queue.put_nowait(uid)
        log.debug('released lock in add_to_run_queue')
        return d

    def _write_exit_code_to_status_json(self, uid, exit_code, blob=None):
        if blob is None:
            blob = self._read_status_blob(self.get_par_dir(uid))
            if not blob:
                blob = {"id": uid}
        blob["exit_code"] = exit_code
        if exit_code == 0:
            blob["status"] = "COMPLETED"
        elif exit_code is not None:
            blob["status"] = "FAILED"
        self._write_status_blob(uid, blob)

    def _write_status_blob(self, uid, blob):
        run_status_json = self.get_status_fp(uid)
        with open(run_status_json, 'w', encoding='utf-8') as outp:
            json.dump(blob, outp)

    def get_par_dir(self, uid):
        return os.path.join(self.top_scratch_dir, uid)

    def get_full_path_to_launcher(self, uid):
        pd = self.get_par_dir(uid)
        return os.path.join(pd, PropinquityRunner._launcher_fn)

    def get_status_fp(self, uid):
        par_dir = self.get_par_dir(uid)
        return os.path.join(par_dir, PropinquityRunner.status_json)

    def read_status_json(self, uid):
        blob = self._read_status_blob(self.get_par_dir(uid))
        if not blob:
            return {"id": uid, 'status': 'ERROR_READING_STATUS'}
        return blob

    def custom_synth_status(self, uid):
        d = self.read_status_json(uid)
        if d is None:
            d = {"id": uid,
                 "status": "UNKNOWN",
                 }
        return d


# Important to keep this restrictive to be Filename legal! see gen_uid
_COLL_NAME_RE = re.compile('^([-a-zA-Z0-9]+)/([-a-zA-Z0-9]+)$')


def validate_custom_synth_args(collection_name, root_id):
    if collection_name is None:
        raise HttpResponseError('Expecting a "input_collection" parameter.', 400)
    coll_owner, coll_name = None, None
    if is_str_type(collection_name):
        try:
            m = _COLL_NAME_RE.match(collection_name)
            assert m
        except:
            pass
        else:
            coll_owner, coll_name = m.groups()
    if coll_owner is None or coll_name is None:
        raise HttpResponseError('Expecting a "input_collection" to have the form "owner_name/collection_name".'
                                ' "{}" did not match this form. Either it is incorrectly formed or our regex for '
                                'recognizing collections names (in ws_wrapper) is too strict.'.format(collection_name),
                                400)
    if root_id is None:
        raise HttpResponseError('Expecting a "root_id" parameter.', 400)
    ott_int = convert_arg_to_ott_int(root_id)
    if ott_int is None:
        raise HttpResponseError('Expecting a "root_id" parameter to be and integer or "ott#"', 400)
    return coll_owner, coll_name, ott_int


def trigger_synth_run(propinquity_runner, coll_owner, coll_name, root_ott_int):
    pr = propinquity_runner
    uid = pr.gen_uid(coll_owner, coll_name, root_ott_int)
    par_dir = os.path.join(pr.top_scratch_dir, uid)
    if os.path.exists(par_dir):
        return pr.custom_synth_status(uid)
    try:
        os.makedirs(par_dir)
    except:
        log.warning("os.makedirs('{par_dir}') failed".format(par_dir=par_dir))
        raise HttpResponseError("Could not create directory for custom synthesis.", 500)
    y = _SYNTH_VAR_CONFIG.format(coll_name=coll_name,
                                 coll_owner=coll_owner,
                                 root_ott_int=root_ott_int,
                                 uid=uid)
    x = _SYNTH_SHELL_TEMPLATE.format(otttag="3.2",
                                     propinq_root=pr.propinq_root,
                                     par_dir=par_dir,
                                     uid=uid,
                                     ott_fp=pr.ott_dir,
                                     base_propinq_ini=pr.propinq_ini_fp,
                                     root_ott_int=root_ott_int,
                                     propinquity_env=pr.propinquity_env)

    with open(os.path.join(par_dir, "var_config.ini"), 'w', encoding='utf-8') as outf:
        outf.write(y)

    bfn = "custom_{uid}.bash".format(uid=uid)
    pbfp = os.path.join(par_dir, bfn)
    with open(pbfp, 'w', encoding='utf-8') as outf:
        outf.write(x)
    mv_and_exe_sh = pr.get_full_path_to_launcher(uid)
    with open(mv_and_exe_sh, 'w', encoding='utf-8') as outf:
        outf.write(_MV_AND_EXE_TEMPLATE.format(par_dir=par_dir,
                                               bash_script=bfn,
                                               propinq_root=pr.propinq_root))
    pr.add_to_run_queue(uid)
    return pr.custom_synth_status(uid)


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
echo $$ > "{par_dir}/running.txt"

if ! cd "{propinq_root}" ; then
    echo 2 > "{par_dir}/exit-code.txt"
    clean_up_running
    exit 1
fi
if ! cp "{par_dir}/{bash_script}" "./{bash_script}"  ; then
    echo 3 > "{par_dir}/exit-code.txt"
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

_SYNTH_VAR_CONFIG = """
[taxonomy]
cleaning_flags = major_rank_conflict,major_rank_conflict_inherited,environmental,viral,barren,not_otu,hidden,was_container,inconsistent,hybrid,merged
additional_regrafting_flags = extinct_inherited,extinct

[synthesis]
collections = {coll_owner}/{coll_name}
root_ott_id = {root_ott_int}
synth_id = custom_{uid}
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

# Prune OTT to root for this subproblem
export OTCETERA_LOGFILE="{par_dir}/otctaxparse.log"
otc-taxonomy-parser -r {root_ott_int} -E --write-taxonomy "{par_dir}/ott{otttag}_pruned_{root_ott_int}" "{ott_fp}" || exit 1
unset OTCETERA_LOGFILE

# Copy the base propinquity config file to extinct_flagged to add the OTT location
cp "{base_propinq_ini}" "{par_dir}/extinct_flagged.ini" || exit 1
echo "ott = {par_dir}/ott{otttag}_pruned_{root_ott_int}" >> "{par_dir}/extinct_flagged.ini" || exit 1

export OTC_CONFIG="{par_dir}/extinct_flagged.ini"
if ! "{propinq_root}/bin/build_at_dir.sh" "{par_dir}/var_config.ini" "{par_dir}/custom_{uid}"
then
    if "{propinq_root}/bin/verify_taxon_edits_not_needed.py" "{par_dir}/custom_{uid}/cleaned_ott/move_extinct_higher_log.json"
    then
       echo 'build failed for reason other than need of taxon bump'
       exit 1
    fi
    "{propinq_root}/bin/patch_taxonomy_by_bumping.py" "{par_dir}/ott{otttag}_pruned_{root_ott_int}" "{par_dir}/custom_{uid}/cleaned_ott/move_extinct_higher_log.json" "{par_dir}/ott{otttag}_bumped_{uid}" || exit
    cp "{base_propinq_ini}" "{par_dir}/extinct_bumped.ini"
    echo "ott = {par_dir}/ott{otttag}_bumped_{uid}" >> "{par_dir}/extinct_bumped.ini"
    export OTC_CONFIG="{par_dir}/extinct_bumped.ini"
    mv "{par_dir}/custom_{uid}" "{par_dir}/pre_bump_custom_{uid}"
    "{propinq_root}/bin/build_at_dir.sh" "{par_dir}/var_config.ini" "{par_dir}/custom_{uid}" || exit 1
fi

cd "{par_dir}" || exit 1
tar cfvz "custom_{uid}.tar.gz" "custom_{uid}"
"""
