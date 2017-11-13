from pyramid.config import Configurator


def main(global_config, **settings):
    """ This function returns a Pyramid WSGI application.
    """
    config = Configurator(settings=settings)
    config.add_route('home', '/')

    config.add_route('tol:about', '/v3/tree_of_life/about')
    config.add_route('tol:node_info', '/v3/tree_of_life/node_info')
    config.add_route('tol:mrca', '/v3/tree_of_life/mrca')
    config.add_route('tol:subtree', '/v3/tree_of_life/subtree')
    config.add_route('tol:induced_subtree', '/v3/tree_of_life/induced_subtree')

    config.add_route('tax:about', '/v3/taxonomy/about')
    config.add_route('tax:taxon_info', '/v3/taxonomy/taxon_info')
    config.add_route('tax:mrca', '/v3/taxonomy/mrca')
    config.add_route('tax:subtree', '/v3/taxonomy/subtree')

    config.add_route('conflict:conflict-status', '/v3/conflict/conflict-status')

    config.scan()
    return config.make_wsgi_app()
