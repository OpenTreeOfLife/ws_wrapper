from pyramid.response import Response
from pyramid.view import view_config


@view_config(route_name='home')
def my_view(request):
    return Response('<body>This is home</body>')
