from pyramid.response import Response
from pyramid.view import view_config
from ws_wrapper.exceptions import HttpResponseError
import requests
from requests.exceptions import ConnectionError

import re

# noinspection PyPackageRequirements
from peyotl.nexson_syntax import PhyloSchema


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
        self.study_prefix = '{}/{}'.format(study.study_url_pref,  self.study_path_prefix)
        self.otc_host = settings['otc.host']
        self.otc_port = settings.get('otc.port', '')
        self.otc_path_prefix = settings.get('otc.prefix', '')
        if self.otc_port:
            self.otc_url_pref = '{}:{}'.format(self.otc_host, self.otc_port)
        else:
            self.otc_url_pref = self.otc_host
        self.otc_prefix = '{}/{}'.format(study.otc_url_pref,  self.otc_path_prefix)

    # We're not really forwarding headers here - does this matter?
    def forward_post_(self, path, **kwargs):
        try:
            method = self.request.method
            fullpath = self.otc_prefix + path
            if method == 'OPTIONS':
                return requests.options(fullpath)
            elif method == 'POST':
                return requests.post(fullpath, **kwargs)
            m = "Refusing to forward method '{}': only forwarding POST and OPTIONS!".format(method)
            raise HttpResponseError(m, 400)
        except ConnectionError:
            msg = "Error: could not connect to otc web services at '{}'".format(self.otc_url_pref)
            raise HttpResponseError(msg, 500)

    def forward_post_json(self, path, **kwargs):
        r = self.forward_post_(path, **kwargs)
        if r.status_code != 200:
            raise HttpResponseError(r.content, r.status_code)
        return r.json()

    def forward_post(self, path, **kwargs):
        r = self.forward_post_(path, **kwargs)
        r.headers.pop('Connection', None)
        return Response(r.content, r.status_code, headers=r.headers)

    def phylesystem_get(self, path):
        url = self.study_prefix + path
        try:
            r = requests.get(url)
        except ConnectionError:
            m = "Error: could not connect to phylesystem api services at '{}'"
            raise HttpResponseError(m.format(self.study_url_pref), 500)
        if r.status_code != 200:
            msg = "Phylesystem request failed:\n URL='{}'\n response code = {}\n message = {}\n"
            msg = msg.format(url, r.status_code, r.content)
            raise HttpResponseError(msg, 500)
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
        return self.forward_post("/tree_of_life/node_info", data=self.request.body)

    @view_config(route_name='tol:mrca')
    def tol_mrca_view(self):
        return self.forward_post("/tree_of_life/mrca", data=self.request.body)

    @view_config(route_name='tol:subtree')
    def tol_subtree_view(self):
        return self.forward_post("/tree_of_life/subtree", data=self.request.body)

    @view_config(route_name='tol:induced_subtree')
    def tol_induced_subtree_view(self):
        return self.forward_post("/tree_of_life/induced_subtree", data=self.request.body)

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
        return self.forward_post('/conflict/conflict-status', json=j)
