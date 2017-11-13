from pyramid.response import Response
from pyramid.view import view_config
import pyramid.httpexceptions

import requests
import json
import peyotl

from peyotl.nexson_syntax import PhyloSchema

# fixme - make the host and port that we are proxying for into variables in
#         development.ini & production.ini

# Do we want to strip the outgroup? (maybe not)
# The tree should have names like nodeYYY - how do we add _ottXXX suffices to leaf node names?
def newick_for_study_tree(study,tree):
    print "study = {} tree = {}".format(study,tree)
    return u"(ott1,ott2,(ott3,ott4));"

def get_newick_tree_from_study(study_nexson, tree):
    ps = PhyloSchema('newick',
                     content='subtree',
                     content_id=(tree,'ingroup'),
                     otu_label='nodeid_ottid')

    return ps.serialize(study_nexson)


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
        return requests.post(self.otc_prefix + path, **kwargs)

    def forward_post(self, path, **kwargs):
        r = self.forward_post_(path, **kwargs)
        if r.status_code != 200:
            raise HTTPException(body=r.content, code=r.status_code)
        return r

    def forward_post_response(self, path, **kwargs):
        r = self.forward_post(path, **kwargs)
        return Response(r.content)

    def phylesystem_get_(self, path):
        study_url = self.study_prefix + path
        print(study_url)
        return requests.get(study_url)

    def phylesystem_get(self, path):
        r = self.phylesystem_get_(path)
        if r.status_code != 200:
            raise HTTPException(body=r.content, code=r.status_code)
        return r

    def get_study_nexson(self, study):
        r = self.phylesystem_get('/study/' + study)
        j = r.json()

        if 'data' in j.keys():
            return j['data']
        else:
            raise HTTPException(body="Error accessing phylesystem study: no 'data' element in reply!", status=500)

    def get_study_tree(self, study, tree):
        study_nexson = self.get_study_nexson(study)
        return get_newick_tree_from_study(study_nexson, tree)

    @view_config(route_name='home')
    def home_view(self):
        return Response('<body>This is home</body>')

    @view_config(route_name='tol:about')
    def tol_about_view(self):
        return self.forward_post_response("/tree_of_life/about")

    @view_config(route_name='tol:node_info')
    def tol_about_view(self):
        return self.forward_post_response("/tree_of_life/node_info", data = self.request.body)

    @view_config(route_name='conflict:conflict-status')
    def conflict_status_view(self):

        j = self.request.json_body

        if 'tree1' in j.keys():
            study1,tree1 = j['tree1'].split('@')
            j.pop('tree1',None)
            j[u'tree1newick'] = self.get_study_tree(study1, tree1)

        return self.forward_post_response('/conflict/conflict-status', json=j)
