from pyramid.response import Response
from pyramid.view import view_config
from ws_wrapper.exceptions import HttpResponseError
try:
    # Python 3
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
except:
    #python 2.7
    from urllib2 import urlencode
    from urllib2 import Request, urlopen
    from urllib2 import HTTPError

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
    return ps.serialize(study_nexson)


# EXCEPTION VIEW. This is how we are supposed to deal with exceptions.
# See https://docs.pylonsproject.org/projects/pyramid/en/1.6-branch/narr/views.html#custom-exception-views
@view_config(context=HttpResponseError)
def generic_exception_catcher(exc, request):
    return Response(exc.body, exc.code)


_singular_ott_node_id = frozenset(['node_id', 'ott_id'])

_plural_ott_node_id = frozenset(['node_ids', 'ott_ids'])


def _merge_ott_and_node_id(p_args):
    node_id = p_args.get('node_id')
    ott_id = p_args.get('ott_id')
    if ott_id:
        if node_id:
            raise HttpResponseError(body='Expecting only one of node_id or ott_id arguments', code=400)
        if not is_int_type(ott_id):
            raise HttpResponseError(body='Expecting "ott_id" to be an integer', code=400)
        node_id = "ott{}".format(ott_id)
    d =  {'node_id': node_id}
    for k, v in p_args.items():
        if k not in _singular_ott_node_id:
            d[k] = v
    return d


def _merge_ott_and_node_ids(p_args):
    node_ids = p_args.get('node_ids', [])
    if not isinstance(node_ids, list):
        raise HttpResponseError(body='Expecting "node_ids" argument to be an array', code=400)
    ott_ids = p_args.get('ott_ids', [])
    if not isinstance(ott_ids, list):
        raise HttpResponseError(body='Expecting "ott_ids" argument to be an array', code=400)
    for o in ott_ids:
        if not is_int_type(o):
            raise HttpResponseError(body='Expecting each element of "ott_ids" to be an integer', code=400)
        node_ids.append("ott{}".format(o))
    d =  {'node_ids': node_ids}
    for k, v in p_args.items():
        if k not in _plural_ott_node_id:
            d[k] = v
    return d


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
    def _request(self, method, url, forward=False, data=None, json_arg=None):
        log.debug('   Performing {} request: URL={}'.format(method, url))
        if data is not None:
            log.debug("      data = {}".format(data))
            data_enc = urlencode(data)
        elif json is not None:
            data_enc = urlencode(json.dump(json_arg))
        else:
            data_enc = None
        if data_enc:
            content_len = len(data_enc)
            headers = {'Content-Type': 'application/json',
                       'Content-Length': content_len}
            req = Request(url=url, data=data_enc, method=method, headers=headers)
        else:
            req = Request(url=url, data=data_enc, method=method)
        try:
            with urlopen(req) as response:
                return req.read()
        except HTTPError:
            m = "Error: could not connect to '{}'\n"
            raise HttpResponseError(m.format(url), 500)


    # We're not really forwarding headers here - does this matter?
    def _forward_post(self, path, data=None, json_arg=None):
        log.debug('Forwarding request: URL={}'.format(path))
        method = self.request.method
        fullpath = self.otc_prefix + path
        if method == 'OPTIONS' or method == 'POST':
            return self._request(method, fullpath, forward=True, data=data, json_arg=json_arg)
        else:
            msg = "Refusing to forward method '{}': only forwarding POST and OPTIONS!".format(method)
            raise HttpResponseError(msg, 400)

    def forward_post(self, path, data=None, json_arg=None):
        rbody = self._forward_post(path, data=data, json_arg=json_arg)
        return Response(rbody, 200)

    def phylesystem_get(self, path):
        url = self.study_prefix + path
        log.debug("Fetching study from phylesystem: PATH={}".format(path));
        r = self._request("GET", url)
        log.debug("Fetching study from phylesystem: SUCCESS!")
        return r

    def phylesystem_get_json(self, path):
        rbody  = self.phylesystem_get(path)
        j = json.loads(rbody)
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
        d = _merge_ott_and_node_id(self.request.json_body)
        return self.forward_post("/tree_of_life/node_info", data=json.dumps(d))

    @view_config(route_name='tol:mrca')
    def tol_mrca_view(self):
        d = _merge_ott_and_node_ids(self.request.json_body)
        return self.forward_post("/tree_of_life/mrca", data=json.dumps(d))

    @view_config(route_name='tol:subtree')
    def tol_subtree_view(self):
        d = _merge_ott_and_node_id(self.request.json_body)
        return self.forward_post("/tree_of_life/subtree", data=json.dumps(d))

    @view_config(route_name='tol:induced_subtree')
    def tol_induced_subtree_view(self):
        d = _merge_ott_and_node_ids(self.request.json_body)
        return self.forward_post("/tree_of_life/induced_subtree", data=json.dumps(d))

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
            j = {u'tree1': self.request.GET['tree1'], u'tree2': self.request.GET['tree2']}
            self.request.method = 'POST'
        else:
            j = self.request.json_body
        if 'tree1' in j.keys():
            study1, tree1 = re.split('[@#]', j['tree1'])
            j.pop('tree1', None)
            j[u'tree1newick'] = self.get_study_tree(study1, tree1)
        return self.forward_post('/conflict/conflict-status', json_arg=j)
