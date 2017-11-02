from pyramid.response import Response
from pyramid.view import view_config

import requests
import peyotl

# fixme - make the host and port that we are proxying for into variables in
#         development.ini & production.ini

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
    r = requests.post("http://localhost:1984/v3/conflict/conflict-status", json = j)
    return Response(r.content, r.status_code)
