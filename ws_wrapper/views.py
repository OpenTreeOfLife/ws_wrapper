from pyramid.response import Response
from pyramid.view import view_config
from ws_wrapper.exceptions import HttpResponseError

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
    from urllib import urlencode
    # noinspection PyCompatibility
    from urllib2 import HTTPError, URLError, Request, urlopen

    def encode_request_data(ds):
        return ds


from peyotl.utility.str_util import is_int_type, is_str_type
import json
import re

# noinspection PyPackageRequirements
from peyotl.nexson_syntax import PhyloSchema

import logging

log = logging.getLogger('ws_wrapper')


# Do we want to strip the outgroup? If we do, it matches propinquity.
def get_newick_tree_from_study(study_nexson, tree):
    ps = PhyloSchema('newick',
                     content='subtree',
                     content_id=(tree, 'ingroup'),
                     otu_label='_nodeid_ottid')
    newick = ps.serialize(study_nexson)

    # Try again if there is no ingroup!
    if not newick:
        log.debug('Attempting to get newick for tree {} but got "{}"!'.format(tree, newick))
        log.debug('Retrying newick parsing without reference to an ingroup.')
        ps = PhyloSchema('newick',
                         content='subtree',
                         content_id=(tree, None),
                         otu_label='_nodeid_ottid')
        newick = ps.serialize(study_nexson)

    if not newick:
        log.debug('Second attempt to get newick failed.')
        raise HttpResponseError("Failed to extract newick tree {} from nexson!".format(tree), 500)
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
def _http_request_or_excep(method, url, data=None, headers={}):
    log.debug('   Performing {} request: URL={}'.format(method, url))
    try:
        if isinstance(data, dict):
            data = json.dumps(data)
    except Exception:
        log.warn('could not encode dict json: {}'.format(repr(data)))

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
    except URLError as err:
        raise HttpResponseError("Error: could not connect to '{}'".format(url), 500)

def is_study_tree(x):
    if re.match('[^()[\]]+[@#][^()[\]]+', x):
        return re.split('[@#]', x)
    else:
        return None


# ROUTE VIEWS
class WSView:
    # noinspection PyUnresolvedReferences
    def __init__(self, request):
        self.request = request
        settings = self.request.registry.settings
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

    def _forward_post(self, fullpath, data=None, headers={}):
        # If `data` ends up being too big, we could print just the first 1k bytes or something.
        log.debug('Forwarding request: URL={} data={}'.format(fullpath,data))
        method = self.request.method
        if method == 'OPTIONS' or method == 'POST':
            r = _http_request_or_excep(method, fullpath, data=data, headers=headers)
#            log.debug('   Returning response "{}"'.format(r))
            return r
        else:
            msg = "Refusing to forward method '{}': only forwarding POST and OPTIONS!"
            raise HttpResponseError(msg.format(method), 400)

    def forward_post_to_otc(self, path, data=None, headers={}):
        fullpath = self.otc_prefix + path
        r = self._forward_post(fullpath, data=data, headers=headers)
        r.headers.pop('Connection', None)
        return r

    def phylesystem_get(self, study):
        path = '/study/' + study
        url = self.study_prefix + path
        log.debug(f"Fetching study from phylesystem: PATH={path}")
        r = _http_request_or_excep("GET", url)
        log.debug(f"Fetching study from phylesystem: {r.status_code}")
        if r.status_code == 404:
            raise HttpResponseError(f"Phylesystem: study {study} not found in {self.study_prefix}!", 500)
        elif r.status_code != 200:
            raise HttpResponseError(f"Phylesystem: failure fetching study {study} from {self.study_prefix}: code = {r.status_code}!", 500)
        return r

    def phylesystem_get_json(self, study):
        r = self.phylesystem_get(study)
        j = json.loads(r.body)
        if 'data' not in j.keys():
            raise HttpResponseError("Error accessing phylesystem: no 'data' element in reply!", 500)
        return j['data']

    def get_study_nexson(self, study):
        return self.phylesystem_get_json(study)

    def get_study_tree(self, study, tree):
        study_nexson = self.get_study_nexson(study)
        return get_newick_tree_from_study(study_nexson, tree)

    @view_config(route_name='home')
    def home_view(self):
        return Response('<body>This is home</body>')

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
        if self.request.method == "OPTIONS":
            return self.forward_post_to_otc("/conflict/conflict-status", data=self.request.body)
        elif self.request.method == "GET":
            if 'tree1' not in self.request.GET:
                raise HttpResponseError("ws_wrapper:conflict-status [translating GET->POST]: Missing required argument 'tree1'", 400)

            if 'tree2' not in self.request.GET:
                raise HttpResponseError("ws_wrapper:conflict-status [translating GET->POST]: Missing required argument 'tree2'", 400)

            j = {u'tree1': self.request.GET['tree1'], u'tree2': self.request.GET['tree2']}

            self.request.method = 'POST'
        else:
            j = get_json(self.request.body)

        if 'tree1' in j.keys():
            if not is_study_tree(j['tree1']):
                raise HttpResponseError(f"ws_wrapper: could not split '{j['tree1']}' into study and tree", 500)
            study1, tree1 = is_study_tree(j['tree1'])
            j.pop('tree1', None)
            j[u'tree1newick'] = self.get_study_tree(study1, tree1)

        if 'tree2' in j.keys() and is_study_tree(j['tree2']):
            study2, tree2 = is_study_tree(j['tree2'])
            j.pop('tree2', None)
            j[u'tree2'] = self.get_study_tree(study2, tree2)

        return self.forward_post_to_otc('/conflict/conflict-status', data=json.dumps(j))
