from pyramid.paster import get_app, setup_logging
ini_path = '/home/otcetera/repo/ws_wrapper/wswrapper.ini'
setup_logging(ini_path)
application = get_app(ini_path, 'main')
