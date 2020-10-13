#!/usr/bin/env python3
from ws_wrapper.exceptions import HttpResponseError
from ws_wrapper.util import convert_arg_to_ott_int
from peyotl.utility.str_util import is_str_type
# import hashlib
import logging
import json
import re
import os

log = logging.getLogger('ws_wrapper')

class PropinquityRunner(object):
    """Class for coordinating on-demand runs of propinquity"""
    status_json = 'run_status.json'
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

    def add_to_run_queue(self, uid, working_dir, invocation):
        run_status_json = self.get_status_fp(uid)
        d = {"id": uid, "dir": working_dir, "command": invocation, "status": "QUEUED"}
        with open(run_status_json, 'w', encoding='utf-8') as outp:
            json.dump(d, outp)
        return d

    def get_status_fp(self, uid):
        par_dir = os.path.join(self.top_scratch_dir, uid)
        return os.path.join(par_dir, PropinquityRunner.status_json)

    def read_status_json(self, uid):
        sj = self.get_status_fp(uid)
        try:
            return json.load(open(sj, 'r', encoding='utf-8'))
        except:
            if os.path.exist(sj):
                return {"id": uid, 'status': 'ERROR_READING_STATUS'}
            return None

    def custom_synth_status(self, uid):
        d = self.read_status_json(uid)
        return {"id": uid, 'status': 'UNKNOWN'} if d is None else d

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
        raise HttpResponseError("Could not create directory for custom synthesis.")
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
                                     root_ott_int=root_ott_int)

    with open(os.path.join(par_dir, "var_config.ini"), 'w', encoding='utf-8') as outf:
        outf.write(y)

    with open(os.path.join(par_dir, "custom_synth.bash"), 'w', encoding='utf-8') as outf:
        outf.write(x)
    pr.add_to_run_queue(uid, working_dir=par_dir, invocation=["bash", "custom_synth.bash"])
    return pr.custom_synth_status(uid)


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
# Prune OTT to root for this subproblem
otc-taxonomy-parser -r {root_ott_int} -E --write-taxonomy "{par_dir}/ott{otttag}_pruned_{root_ott_int}" "{ott_fp}" || exit 1

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
    "{propinq_root}/bin/build_at_dir.sh" var_config.ini"{par_dir}/custom_{uid}" || exit 1
fi

"""