from pyramid.response import Response
from pyramid.view import view_config

import requests
import json
import peyotl

from peyotl.nexson_syntax import PhyloSchema

study_host = 'https://api.opentreeoflife.org'
study_prefix = '/v3/study/'

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
    j = request.json_body
    if 'tree1' in j.keys():
        study1,tree1 = j['tree1'].split('@')
        study_nexson = requests.get(study_host+study_prefix+study1).json()['data']
        ps = PhyloSchema('newick', content='subtree', content_id=(tree1,'ingroup'))
        print(ps.serialize(study_nexson))
        if False:
            j.pop('tree1',None)
            j[u'tree1newick'] = newick_for_study_tree(study, tree)

    r = requests.post("http://localhost:1984/v3/conflict/conflict-status", json = j)
    return Response(r.content, r.status_code)
