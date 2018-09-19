from pyramid.response import Response
from pyramid.view import view_config
from ws_wrapper.exceptions import HttpResponseError
import requests
from requests.exceptions import ConnectionError
from peyotl.utility.str_util import is_int_type
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
                     otu_label='nodeid_ottid')
    newick = ps.serialize(study_nexson)

    # Try again if there is no ingroup!
    if not newick:
        log.debug('Attempting to get newick but got "{}"!'.format(newick))
        log.debug('Retrying newick parsing without reference to an ingroup.')
        ps = PhyloSchema('newick',
                         content='subtree',
                         content_id=(tree,None),
                         otu_label='nodeid_ottid')
        newick = ps.serialize(study_nexson)

    if not newick:
        log.debug('Second attempt to get newick failed.')
        raise HttpResponseError("Failed to extract newick tree from nexson!", 500)
    return newick


# EXCEPTION VIEW. This is how we are supposed to deal with exceptions.
# See https://docs.pylonsproject.org/projects/pyramid/en/1.6-branch/narr/views.html#custom-exception-views
@view_config(context=HttpResponseError)
def generic_exception_catcher(exc, request):
    return Response(exc.body, exc.code)


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
    if isinstance(o,str) or isinstance(unicode):
        try:
            o = int(o)
        except:
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
        raise HttpResponseError(body='Expecting "ott_id" to be an integer, but got "{}"'.format(ott_id), code=400)

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
            raise HttpResponseError(body='Expecting each element of "ott_ids" to be an integer, but got element "{}"'.format(o), code=400)
        node_ids.append("ott{}".format(o))

        j_args['node_ids'] = node_ids

    return json.dumps(j_args)



# ROUTE VIEWS
class WSView:
    # noinspection PyUnresolvedReferences
    def __init__(self, request):
        self.request = request
        settings = self.request.registry.settings
        self.study_host = settings['phylesystem-api.host']
        self.study_port = settings.get('phylesystem-api.port', '')
        if self.study_port:
            self.study_url_pref = '{}:{}'.format(self.study_host, self.study_port)
        else:
            self.study_url_pref = self.study_host
        self.study_path_prefix = settings.get('phylesystem-api.prefix', '')
        self.study_prefix = '{}/{}'.format(self.study_url_pref,  self.study_path_prefix)
        self.otc_host = settings['otc.host']
        self.otc_port = settings.get('otc.port', '')
        self.otc_path_prefix = settings.get('otc.prefix', '')
        if self.otc_port:
            self.otc_url_pref = '{}:{}'.format(self.otc_host, self.otc_port)
        else:
            self.otc_url_pref = self.otc_host
        self.otc_prefix = '{}/{}'.format(self.otc_url_pref,  self.otc_path_prefix)

    # Unify logging and error handling code here instead of duplicating it everywhere.
    def _request(self, method, url, forward=False, **kwargs):
        log.debug('   Performing {} request: URL={}'.format(method, url))
        if "data" in kwargs:
            log.debug("      data = {}".format(kwargs["data"]))
        try:
            r = requests.request(method, url, **kwargs)
        except ConnectionError:
            m = "Error: could not connect to '{}'\n"
            raise HttpResponseError(m.format(url), 500)
        if r.status_code != 200:
            msg = "{} request failed:\n URL='{}'\n response code = {}\n message = {}\n"
            msg = msg.format(method, url, r.status_code, r.content)
            if forward:
                log.warn(msg.rstrip())
                log.warn('   Forwarding failed {} request back to client.\n'.format(method))
            else:
                raise HttpResponseError(msg, 500)
        else:
            log.debug('   SUCCESS for {} request: len(content) = {}\n'.format(method, len(r.content)))
        return r

    # We're not really forwarding headers here - does this matter?
    def _forward_post(self, path, **kwargs):
        log.debug('Forwarding request: URL={}'.format(path))
        method = self.request.method
        fullpath = self.otc_prefix + path
        if method == 'OPTIONS' or method == 'POST':
            return self._request(method, fullpath, forward=True, **kwargs)
        else:
            msg = "Refusing to forward method '{}': only forwarding POST and OPTIONS!".format(method)
            raise HttpResponseError(msg, 400)

    def forward_post_json(self, path, **kwargs):
        r = self._forward_post(path, **kwargs)
        if r.status_code != 200:
            raise HttpResponseError(r.content, r.status_code)
        return r.json()

    def forward_post(self, path, **kwargs):
        r = self._forward_post(path, **kwargs)
        r.headers.pop('Connection', None)
        return Response(r.content, r.status_code, headers=r.headers)

    def phylesystem_get(self, path):
        url = self.study_prefix + path
        log.debug("Fetching study from phylesystem: PATH={}".format(path));
        r = self._request("GET", url)
        log.debug("Fetching study from phylesystem: SUCCESS!")
        return r

    def phylesystem_get_json(self, path):
        r = self.phylesystem_get(path)
        j = r.json()
        if 'data' not in j.keys():
            raise HttpResponseError("Error accessing phylesystem: no 'data' element in reply!", 500)
        return j['data']

    def get_study_nexson(self, study):
        return self.phylesystem_get_json('/study/' + study)

    def get_study_tree(self, study, tree):
        study_nexson = self.get_study_nexson(study)
        return get_newick_tree_from_study(study_nexson, tree)

    @view_config(route_name='home')
    def home_view(self):
        return Response('<body>This is home</body>')

    @view_config(route_name='tol:about')
    def tol_about_view(self):
        return self.forward_post("/tree_of_life/about", data=self.request.body)

    @view_config(route_name='tol:node_info')
    def tol_node_info_view(self):
        d = _merge_ott_and_node_id(self.request.body)
        return self.forward_post("/tree_of_life/node_info", data=d)

    @view_config(route_name='tol:mrca')
    def tol_mrca_view(self):
        d = _merge_ott_and_node_ids(self.request.body)
        return self.forward_post("/tree_of_life/mrca", data=d)

    @view_config(route_name='tol:subtree')
    def tol_subtree_view(self):
        d = _merge_ott_and_node_id(self.request.body)
        return self.forward_post("/tree_of_life/subtree", data=d)

    @view_config(route_name='tol:induced_subtree')
    def tol_induced_subtree_view(self):
        d = _merge_ott_and_node_ids(self.request.body)
        return self.forward_post("/tree_of_life/induced_subtree", data=d)

    @view_config(route_name='tax:about')
    def tax_about_view(self):
        return self.forward_post("/taxonomy/about", data=self.request.body)

    @view_config(route_name='tax:taxon_info')
    def tax_taxon_info_view(self):
        return self.forward_post("/taxonomy/taxon_info", data=self.request.body)

    @view_config(route_name='tax:mrca')
    def tax_mrca_view(self):
        return self.forward_post("/taxonomy/mrca", data=self.request.body)

    @view_config(route_name='tax:subtree')
    def tax_subtree_view(self):
        return self.forward_post("/taxonomy/subtree", data=self.request.body)

    @view_config(route_name='conflict:conflict-status')
    def conflict_status_view(self):
        if self.request.method == "GET":
            if 'tree1' in self.request.GET and 'tree2' in self.request.GET:
                j = {u'tree1': self.request.GET['tree1'], u'tree2': self.request.GET['tree2']}
                self.request.method = 'POST'
            else:
                log.debug("self.request.GET={}".format(self.request.GET))
                raise HttpResponseError("ws_wrapper:conflict-status [translating GET->POST]:\n  Expecting arguments 'tree1' and 'tree2', but got:\n{}\n".format(self.request.GET), 400)
        else:
            j = get_json(self.request.body)
        if 'tree1' in j.keys():
            study1, tree1 = re.split('[@#]', j['tree1'])
            j.pop('tree1', None)
            j[u'tree1newick'] = self.get_study_tree(study1, tree1)
        return self.forward_post('/conflict/conflict-status', json=j)
