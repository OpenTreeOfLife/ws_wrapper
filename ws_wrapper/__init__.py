from pyramid.config import Configurator
import logging

log = logging.getLogger('ws_wrapper')


# noinspection PyUnusedLocal
def main(global_config, **settings):

    log.debug("Starting ws_wrapper...")
    """ This function returns a Pyramid WSGI application.
    """
    config = Configurator(settings=settings)
    config.add_route('home', '/')
    log.debug("Read configuration...")

    config.add_route('tol:about', '/v3/tree_of_life/about')
    config.add_route('tol:node_info', '/v3/tree_of_life/node_info')
    config.add_route('tol:mrca', '/v3/tree_of_life/mrca')
    config.add_route('tol:subtree', '/v3/tree_of_life/subtree')
    config.add_route('tol:induced_subtree', '/v3/tree_of_life/induced_subtree')

    config.add_route('tax:about', '/v3/taxonomy/about')
    config.add_route('tax:flags', '/v3/taxonomy/flags')
    config.add_route('tax:taxon_info', '/v3/taxonomy/taxon_info')
    config.add_route('tax:mrca', '/v3/taxonomy/mrca')
    config.add_route('tax:subtree', '/v3/taxonomy/subtree')

    config.add_route('tnrs:match_names', '/v3/tnrs/match_names')
    config.add_route('tnrs:autocomplete_name', '/v3/tnrs/autocomplete_name')
    config.add_route('tnrs:contexts', '/v3/tnrs/contexts')
    config.add_route('tnrs:infer_context', '/v3/tnrs/infer_context')

    config.add_route('conflict:conflict-status', '/v3/conflict/conflict-status')

    config.add_route('tol:build-tree', '/v3/tree_of_life/build_tree')
    config.add_route('tol:custom-built-tree',
                     r'/v3/tree_of_life/custom_built_tree/{build_id}.{ext:(tar\.gz|tgz|zip)}')
    config.add_route('tol:list-custom-built-trees', '/v3/tree_of_life/list_custom_built_trees')

    config.scan()
    log.debug("Added routes.")
    return config.make_wsgi_app()
