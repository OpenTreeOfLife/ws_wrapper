from pyramid.response import Response
from pyramid.view import view_config

import requests

@view_config(route_name='home')
def home_view(request):
    return Response('<body>This is home</body>')

@view_config(route_name='tol:about')
def tol_about_view(request):
    r = requests.post("http://localhost:1984/v3/tree_of_life/about")
    return Response(r.content)
