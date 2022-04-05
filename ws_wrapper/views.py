from pyramid.response import Response, FileResponse
from pyramid.view import view_config
from ws_wrapper.exceptions import HttpResponseError
from ws_wrapper.build_tree import (PropinquityRunner,
                                   validate_custom_synth_args,
                                   )
from threading import Lock
import os

try:
    # Python 3
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen

    def encode_request_data(ds):
        if isinstance(ds, str):
            return ds.encode('utf-8')
        return ds

    from urllib.error import HTTPError, URLError
except ImportError:
    # python 2.7
    # noinspection PyUnresolvedReferences
    from urllib import urlencode
    # noinspection PyCompatibility,PyUnresolvedReferences
    from urllib2 import HTTPError, URLError, Request, urlopen

    def encode_request_data(ds):
        return ds


from peyutil import is_str_type, is_int_type
import json
import re

# noinspection PyPackageRequirements
from peyotl.nexson_syntax import PhyloSchema



import logging

log = logging.getLogger('ws_wrapper')



try:
    from chronosynth import chronogram
    dates = chronogram.build_synth_node_source_ages()
    log.debug("CHRONO TRUE")
    CHRONO = True
except:
    log.debug("CHRONO FALSE")
    CHRONO = False


    


# Do we want to strip the outgroup? If we do, it matches propinquity.
def get_newick_tree_from_study(study_nexson, tree):
    ps = PhyloSchema('newick',
                     content='subtree',
                     content_id=(tree, 'ingroup'),
                     otu_label='_nodeid_ottid')
    newick = ps.serialize(study_nexson)

    # Try again if there is no ingroup!
    if not newick:
        log.debug('Attempting to get newick but got "{}"!'.format(newick))
        log.debug('Retrying newick parsing without reference to an ingroup.')
        ps = PhyloSchema('newick',
                         content='subtree',
                         content_id=(tree, None),
                         otu_label='_nodeid_ottid')
        newick = ps.serialize(study_nexson)

    if not newick:
        log.debug('Second attempt to get newick failed.')
        raise HttpResponseError("Failed to extract newick tree from nexson!", 500)
    return newick


# EXCEPTION VIEW. This is how we are supposed to deal with exceptions.
# See https://docs.pylonsproject.org/projects/pyramid/en/1.6-branch/narr/views.html#custom-exception-views
# noinspection PyUnusedLocal
@view_config(context=HttpResponseError)
def generic_exception_catcher(exc, request):
    return Response(exc.body, exc.code, headers={'Content-Type': 'application/json'})


def get_json_or_none(body):
    # Don't give an unexplained internal server error if the JSON is malformed.
    try:
        j = json.loads(body)
        return j
    except ValueError:
        return None


def get_json(body):
    # Note that otc-tol-ws treats '' as '{}'.
    # That should probably be replicated here (or changed in otc-tol-ws),
    #   except that we currently avoid transforming badly formed JSON, and hand it
    #   to otc-tol-ws unmodified.

    j = get_json_or_none(body)
    if not j:
        raise HttpResponseError("Could not get JSON from body {}".format(body), 400)
    return j


def try_convert_to_integer(o):
    if is_str_type(o):
        try:
            return int(o)
        except TypeError:
            pass
    return o

def _merge_ott_and_node_id(body):
    # If the JSON doesn't parse, get out of the way and let otc-tol-ws handle the errors.
    j_args = get_json_or_none(body)
    if not j_args:
        return body
    # Only modify the JSON if there is something to do.
    if 'ott_id' not in j_args:
        return body
    # Only modify the JSON if there is something to do.
    if 'node_id' in j_args:
        raise HttpResponseError(body='Expecting only one of node_id or ott_id arguments', code=400)
    ott_id = j_args.pop('ott_id')
    # Convert string to integer... to handle old peyotl
    ott_id = try_convert_to_integer(ott_id)
    if not is_int_type(ott_id):
        raise HttpResponseError(
            body='Expecting "ott_id" to be an integer, but got "{}"'.format(ott_id), code=400)
    j_args['node_id'] = "ott{}".format(ott_id)

    return json.dumps(j_args)


def _merge_ott_and_node_ids(body):
    # If the JSON doesn't parse, get out of the way and let otc-tol-ws handle the errors.
    j_args = get_json_or_none(body)
    if not j_args:
        return body

    # Only modify the JSON if there is something to do.
    if 'ott_ids' not in j_args:
        return body

    node_ids = j_args.pop('node_ids', [])
    log.debug('node_ids = "{}"'.format(node_ids))
    # Handle "node_ids": null
    if node_ids is None:
        node_ids = []

    if not isinstance(node_ids, list):
        raise HttpResponseError(body='Expecting "node_ids" argument to be an array', code=400)

    ott_ids = j_args.pop('ott_ids', [])
    if ott_ids is None:
        ott_ids = []

    if not isinstance(ott_ids, list):
        raise HttpResponseError(body='Expecting "ott_ids" argument to be an array', code=400)

    # Append the ott_ids after the node_ids
    for o in ott_ids:
        # Convert string to integer... to handle old peyotl
        o = try_convert_to_integer(o)
        if not is_int_type(o):
            raise HttpResponseError(
                body='Expecting each element of "ott_ids" to be an integer, but got element "{}"'.format(
                    o), code=400)
        node_ids.append("ott{}".format(o))
        j_args['node_ids'] = node_ids

    return json.dumps(j_args)

# This method needs to return a Response object (See `from pyramid.response import Response`)
def _http_request_or_excep(method, url, data=None, headers=None):
    if headers is None:
        headers = {}
    log.debug('   Performing {} request: URL={}'.format(method, url))
    try:
        if isinstance(data, dict):
            data = json.dumps(data)
    except Exception:
        log.warning('could not encode dict json: {}'.format(repr(data)))

    headers['Content-Type'] = 'application/json'
    req = Request(url=url, data=encode_request_data(data), headers=headers)
    req.get_method = lambda: method
    try:
        # this raises an exception if resp.code isn't 200, which is ridiculous
        resp = urlopen(req)
        headerobj = resp.info()
        return Response(resp.read(), resp.code, headers=headerobj)
    except HTTPError as err:
        try:
            return Response(err.read(), err.code, headers=err.info())
        except:
            raise HttpResponseError(err.reason, err.code)
    except URLError:
        raise HttpResponseError("Error: could not connect to '{}'".format(url), 500)

PROPINQUITY_RUNNER = None
PROPINQUITY_RUNNER_LOCK = Lock()


# ROUTE VIEWS
class WSView:
    # noinspection PyUnresolvedReferences
    def __init__(self, request):
        self.request = request
        settings = self.request.registry.settings
        self.settings = settings
        self.study_host = settings.get('phylesystem-api.host', 'https://api.opentreeoflife.org')
        self.study_port = settings.get('phylesystem-api.port', '')
        if self.study_port:
            self.study_url_pref = '{}:{}'.format(self.study_host, self.study_port)
        else:
            self.study_url_pref = self.study_host
        self.study_path_prefix = settings.get('phylesystem-api.prefix', '')
        self.study_prefix = '{}/{}'.format(self.study_url_pref, self.study_path_prefix)
        self.otc_host = settings.get('otc.host', 'http://localhost')
        self.otc_port = settings.get('otc.port', '1984')
        self.otc_path_prefix = settings.get('otc.prefix', 'v3')
        if self.otc_port:
            self.otc_url_pref = '{}:{}'.format(self.otc_host, self.otc_port)
        else:
            self.otc_url_pref = self.otc_host
        self.otc_prefix = '{}/{}'.format(self.otc_url_pref, self.otc_path_prefix)

    @property
    def propinquity_runner(self):
        """Access to the global PROPINQUITY_RUNNER (with lazy, locked creation)."""
        global PROPINQUITY_RUNNER
        if PROPINQUITY_RUNNER is None:
            with PROPINQUITY_RUNNER_LOCK:
                if PROPINQUITY_RUNNER is None:
                    PROPINQUITY_RUNNER = PropinquityRunner(self.settings)
        return PROPINQUITY_RUNNER

    def _forward_post(self, fullpath, data=None, headers=None):
        # If `data` ends up being too big, we could print just the first 1k bytes or something.
        log.debug('Forwarding request: URL={} data={}'.format(fullpath, data))
        method = self.request.method
        if method == 'OPTIONS' or method == 'POST':
            r = _http_request_or_excep(method, fullpath, data=data, headers=headers)
            # log.debug('   Returning response "{}"'.format(r))
            return r
        else:
            msg = "Refusing to forward method '{}': only forwarding POST and OPTIONS!"
            raise HttpResponseError(msg.format(method), 400)

    def forward_post_to_otc(self, path, data=None, headers=None):
        fullpath = self.otc_prefix + path
        r = self._forward_post(fullpath, data=data, headers=headers)
        r.headers.pop('Connection', None)
        return r

    def phylesystem_get(self, path):
        url = self.study_prefix + path
        log.debug("Fetching study from phylesystem: PATH={}".format(path))
        r = _http_request_or_excep("GET", url)
        log.debug("Fetching study from phylesystem: SUCCESS!")
        return r

    def phylesystem_get_json(self, path):
        r = self.phylesystem_get(path)
        j = json.loads(r.body)
        if 'data' not in j.keys():
            raise HttpResponseError("Error accessing phylereturn system: no 'data' element in reply!", 500)
        return j['data']

    def get_study_nexson(self, study):
        return self.phylesystem_get_json('/study/' + study)

    def get_study_tree(self, study, tree):
        study_nexson = self.get_study_nexson(study)
        return get_newick_tree_from_study(study_nexson, tree)

    @view_config(route_name='home')
    def home_view(self):
        return Response('<body>This is Open Tree of Life ws_wrapper home</body>')

    @view_config(route_name='tol:about')
    def tol_about_view(self):
        return self.forward_post_to_otc("/tree_of_life/about", data=self.request.body)

    @view_config(route_name='tol:node_info')
    def tol_node_info_view(self):
        d = _merge_ott_and_node_id(self.request.body)
        return self.forward_post_to_otc("/tree_of_life/node_info", data=d)

    @view_config(route_name='tol:mrca')
    def tol_mrca_view(self):
        d = _merge_ott_and_node_ids(self.request.body)
        return self.forward_post_to_otc("/tree_of_life/mrca", data=d)

    @view_config(route_name='tol:subtree')
    def tol_subtree_view(self):
        d = _merge_ott_and_node_id(self.request.body)
        return self.forward_post_to_otc("/tree_of_life/subtree", data=d)

    @view_config(route_name='tol:induced_subtree')
    def tol_induced_subtree_view(self):
        d = _merge_ott_and_node_ids(self.request.body)
        return self.forward_post_to_otc("/tree_of_life/induced_subtree", data=d)

    @view_config(route_name='tax:about')
    def tax_about_view(self):
        return self.forward_post_to_otc("/taxonomy/about", data=self.request.body)

    @view_config(route_name='tax:taxon_info')
    def tax_taxon_info_view(self):
        return self.forward_post_to_otc("/taxonomy/taxon_info", data=self.request.body)

    @view_config(route_name='tax:mrca')
    def tax_flags_view(self):
        return self.forward_post_to_otc("/taxonomy/mrca", data=self.request.body)

    @view_config(route_name='tax:flags')
    def tax_mrca_view(self):
        return self.forward_post_to_otc("/taxonomy/flags", data=self.request.body)

    @view_config(route_name='tax:subtree')
    def tax_subtree_view(self):
        return self.forward_post_to_otc("/taxonomy/subtree", data=self.request.body)

    @view_config(route_name='tnrs:match_names')
    def tnrs_match_names_view(self):
        return self.forward_post_to_otc("/tnrs/match_names", data=self.request.body)

    @view_config(route_name='tnrs:autocomplete_name')
    def tnrs_autocomplete_name_view(self):
        return self.forward_post_to_otc("/tnrs/autocomplete_name", data=self.request.body)

    @view_config(route_name='tnrs:contexts')
    def tnrs_contexts_view(self):
        return self.forward_post_to_otc("/tnrs/contexts", data=self.request.body)

    @view_config(route_name='tnrs:infer_context')
    def tnrs_infer_context_view(self):
        return self.forward_post_to_otc("/tnrs/infer_context", data=self.request.body)

    @view_config(route_name='conflict:conflict-status')
    def conflict_status_view(self):
        if self.request.method == "GET":
            if 'tree1' in self.request.GET and 'tree2' in self.request.GET:
                j = {u'tree1': self.request.GET['tree1'], u'tree2': self.request.GET['tree2']}
                self.request.method = 'POST'
            else:
                log.debug("self.request.GET={}".format(self.request.GET))
                raise HttpResponseError(
                    "ws_wrapper:conflict-status [translating GET->POST]:\n  Expecting arguments 'tree1' and 'tree2', but got:\n{}\n".format(
                        self.request.GET), 400)
        else:
            j = get_json(self.request.body)
        if 'tree1' in j.keys():
            study1, tree1 = re.split('[@#]', j['tree1'])
            j.pop('tree1', None)
            j[u'tree1newick'] = self.get_study_tree(study1, tree1)
        return self.forward_post_to_otc('/conflict/conflict-status', data=json.dumps(j))

    @view_config(route_name='dates:synth_node_age', renderer='json')
    def synth_node_age_view(self):
        if CHRONO:
            log.debug("CHRONO TRUE")
            node_id = self.request.matchdict['node']
            ret = chronogram.synth_node_source_ages(node_id)
            return ret
        else:
            return {'msg': 'dates services (chronosynth) not installed on this machine'}


    @view_config(route_name='dates:dated_tree', renderer='json')
    def dated_subtree_view(self):
        if CHRONO:
            if self.request.method == "POST":
                data = json.loads(self.request.body)
                max_age = None
                if 'max_age' in data:
                    max_age = max_age
                if 'node_id' in data:
                    ret = chronogram.date_synth_subtree(node_id=data['node_id'], max_age=max_age, method='bladj')
                if 'node_ids' in data:
                    ret = chronogram.date_synth_subtree(node_ids=data['node_ids'], max_age=max_age, method='bladj')
                ### Make it work with other node idsssss
                return ret
        else:
            return {'msg': 'dates services (chronosynth) not installed on this machine'}

    @view_config(route_name='dates:dated_nodes_dump', renderer='json')
    def all_dated_nodes_dump(self):
        if CHRONO:
            ret = chronogram.build_synth_node_source_ages()
            ### Make it work with other node idsssss
            return ret
        else:
            return {'msg': 'dates services (chronosynth) not installed on this machine'}


    @view_config(route_name='dates:update_dated_nodes', renderer='json')
    def update_all_dated_nodes(self):
        if CHRONO:
            chronogram.build_synth_node_source_ages(fresh=True)
            ### Make it work with other node idsssss
            return {'msg':'update complete'}
        else:
            return {'msg': 'dates services (chronosynth) not installed on this machine'}

        

    @view_config(route_name='tol:build-tree', request_method="OPTIONS")
    def build_tree_options(self):
        headers = {'Access-Control-Allow-Credentials': 'true',
                   'Access-Control-Allow-Headers': 'content-type',
                   'Access-Control-Allow-Methods': 'POST',
                   'Access-Control-Allow-Origin': '*',
                   'Access-Control-Max-Age': '86400', }
        return Response(body=None, status=200, headers=headers)

    @view_config(route_name='tol:build-tree', request_method="POST")
    def build_tree(self):
        headers = {'Content-Type': 'application/json'}
        j = get_json(self.request.body)
        inp_coll = j.get('input_collection')
        root_id_str = j.get('root_id')
        pr = self.propinquity_runner
        x = validate_custom_synth_args(collection_name=inp_coll,
                                       root_id=root_id_str,
                                       runner=pr)
        user_initiating_run = j.get('user')
        coll_owner, coll_name, ott_int = x
        body = pr.trigger_synth_run(coll_owner=coll_owner,
                                    coll_name=coll_name,
                                    root_ott_int=ott_int,
                                    user_initiating_run=user_initiating_run)
        if isinstance(body, dict):
            body = pr.add_download_url_if_needed(body, self.request)
            body = json.dumps(body)
        return Response(body, 200, headers=headers)

    @view_config(route_name='tol:custom-built-tree', request_method="GET")
    def custom_built_tree(self):
        md = self.request.matchdict
        build_id = md['build_id']
        ext = md['ext']
        pr = self.propinquity_runner
        try:
            fp = pr.get_archive_filepath(self.request, uid=build_id, ext=ext)
        except KeyError:
            raise HttpResponseError('build_id="{}" unknown'.format(build_id), 404)

        if not os.path.isfile(fp):
            raise HttpResponseError("Archive not found", 410)
        response = FileResponse(fp,
                                request=self.request,
                                content_type='application/gzip')
        return response

    @view_config(route_name='tol:list-custom-built-trees', request_method="OPTIONS")
    def list_custom_built_trees_options(self):
        headers = {'Access-Control-Allow-Credentials': 'true',
                   'Access-Control-Allow-Headers': 'content-type',
                   'Access-Control-Allow-Methods': 'POST',
                   'Access-Control-Allow-Origin': '*',
                   'Access-Control-Max-Age': '86400', }
        return Response(body=None, status=200, headers=headers)
      
    @view_config(route_name='tol:list-custom-built-trees', request_method="GET")
    def list_custom_built_trees(self):
        headers = {'Content-Type': 'application/json',
                   'Access-Control-Allow-Credentials': 'true',
                   'Access-Control-Allow-Headers': 'content-type',
                   'Access-Control-Allow-Methods': 'POST',
                   'Access-Control-Allow-Origin': '*',
                   'Access-Control-Max-Age': '86400', }
        pr = self.propinquity_runner
        synth_by_id = pr.get_runs_by_id()
        for uid, blob in synth_by_id.items():
            s = blob.get("status", "")
            if s == "COMPLETED" or s == "FAILED":
                if pr._download_attr not in blob:
                    pr.add_download_url_if_needed(blob, self.request)
        rs = '{}\n'.format(json.dumps(synth_by_id, ensure_ascii=True))
        return Response(rs, 200, headers=headers)
