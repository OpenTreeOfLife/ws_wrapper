from pyramid.response import Response
from pyramid.view import view_config

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

@view_config(route_name='home')
def home_view(request):
    return Response('<body>This is home</body>')

@view_config(route_name='tol:about')
def tol_about_view(request):
    r = requests.post("http://localhost:1984/v3/tree_of_life/about")
    return Response(r.content, r.status_code)

@view_config(route_name='conflict:conflict-status')
def conflict_status_view(request):
    settings = request.registry.settings

    study_host   = settings['phylesystem-api.host']
    study_port   = settings.get('phylesystem-api.port', '')
    study_prefix = settings.get('phylesystem-api.prefix', '')

    otc_host     = settings['otc.host']
    otc_port     = settings.get('otc.port','')
    otc_prefix   = settings.get('otc.prefix','')

    j = request.json_body
    if 'tree1' in j.keys():
        study1,tree1 = j['tree1'].split('@')
        study_url = study_host+':'+study_port+'/'+ study_prefix + '/study/' + study1
        r = requests.get(study_url)
        if r.status_code != 200:
            return Response(r.content, r.status_code)

        # Should we return a useful error message if the JSON object has no 'data' key?
        study_nexson = r.json()['data']
        ps = PhyloSchema('newick',
                         content='subtree',
                         content_id=(tree1,'ingroup'),
                         otu_label='nodeid_ottid')
        j.pop('tree1',None)
        j[u'tree1newick'] = ps.serialize(study_nexson)

    r = requests.post(otc_host+':'+otc_port + '/' +
                      otc_prefix + '/conflict/conflict-status', json = j)
    return Response(r.content, r.status_code)
