from pyramid.response import Response
from pyramid.view import view_config
from ws_wrapper.exceptions import HttpResponseError
import requests
from requests.exceptions import ConnectionError

import json
import re
import peyotl

from peyotl.nexson_syntax import PhyloSchema

# Do we want to strip the outgroup? If we do, it matches propinquity.
def get_newick_tree_from_study(study_nexson, tree):
    ps = PhyloSchema('newick',
                     content='subtree',
                     content_id=(tree,'ingroup'),
                     otu_label='nodeid_ottid')

    return ps.serialize(study_nexson)


# EXCEPTION VIEW. This is how we are supposed to deal with exceptions.
# See https://docs.pylonsproject.org/projects/pyramid/en/1.6-branch/narr/views.html#custom-exception-views
@view_config(context=HttpResponseError)
def generic_exception_catcher(exc, request):
    return Response(exc.body, exc.code)

# ROUTE VIEWS
class WSView:
    def __init__(self, request):
        self.request = request
        settings = self.request.registry.settings

        self.study_host   = settings['phylesystem-api.host']
        self.study_port   = settings.get('phylesystem-api.port', '')
        self.study_path_prefix = settings.get('phylesystem-api.prefix', '')
        self.study_prefix = self.study_host+':'+self.study_port + '/' + self.study_path_prefix

        self.otc_host     = settings['otc.host']
        self.otc_port     = settings.get('otc.port','')
        self.otc_path_prefix   = settings.get('otc.prefix','')
        self.otc_prefix = self.otc_host+':'+self.otc_port + '/' + self.otc_path_prefix

    def forward_post_(self, path, **kwargs):
        try:
            return requests.post(self.otc_prefix + path, **kwargs)
        except ConnectionError:
            if self.otc_port == "":
                host = self.otc_host
            else:
                host = "{}:{}".format(self.otc_host, self.otc_port)
            msg = "Error: could not connect to otc web services at '{}'\n".format(host)
            raise HttpResponseError(msg, 500)

    def forward_post_json(self, path, **kwargs):
        r = self.forward_post_(path, **kwargs)
        if r.status_code != 200:
            raise HTTPResponseError(r.content, r.code)
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
            if self.study_port == "":
                host = self.study_host
            else:
                host = "{}:{}".format(self.study_host, self.study_port)
            raise HttpResponseError("Error: could not connect to phylesystem api services at '{}'\n".format(host), 500)

        if r.status_code != 200:
            msg = "Phylesystem request failed:\n URL='{}'\n response code = {}\n message = {}\n".format(url, r. status_code, r.content)
            raise HttpResponseError(msg, 500)
        return r


    def phylesystem_get_json(self, path):
        r = self.phylesystem_get(path)
        j = r.json()

        if 'data' not in j.keys():
            raise HTTPResponseError("Error accessing phylesystem: no 'data' element in reply!", 500)

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
        return self.forward_post("/tree_of_life/about", data = self.request.body)

    @view_config(route_name='tol:node_info')
    def tol_node_info_view(self):
        return self.forward_post("/tree_of_life/node_info", data = self.request.body)

    @view_config(route_name='tol:mrca')
    def tol_mrca_view(self):
        return self.forward_post("/tree_of_life/mrca", data = self.request.body)

    @view_config(route_name='tol:subtree')
    def tol_subtree_view(self):
        return self.forward_post("/tree_of_life/subtree", data = self.request.body)

    @view_config(route_name='tol:induced_subtree')
    def tol_induced_subtree_view(self):
        return self.forward_post("/tree_of_life/induced_subtree", data = self.request.body)

    @view_config(route_name='tax:about')
    def tax_about_view(self):
        return self.forward_post("/taxonomy/about", data = self.request.body)

    @view_config(route_name='tax:taxon_info')
    def tax_taxon_info_view(self):
        return self.forward_post("/taxonomy/taxon_info", data = self.request.body)

    @view_config(route_name='tax:mrca')
    def tax_mrca_view(self):
        return self.forward_post("/taxonomy/mrca", data = self.request.body)

    @view_config(route_name='tax:subtree')
    def tax_subtree_view(self):
        return self.forward_post("/taxonomy/subtree", data = self.request.body)

    @view_config(route_name='conflict:conflict-status')
    def conflict_status_view(self):
        if self.request.method == "GET":
            j = {}
            j[u'tree1'] = self.request.GET['tree1']
            j[u'tree2'] = self.request.GET['tree2']
        else:
            j = self.request.json_body

        if 'tree1' in j.keys():
            study1,tree1 = re.split('@|#', j['tree1'])
            j.pop('tree1',None)
            j[u'tree1newick'] = self.get_study_tree(study1, tree1)

        return self.forward_post('/conflict/conflict-status', json=j)
