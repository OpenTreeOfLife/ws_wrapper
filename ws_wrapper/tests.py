import unittest
import configparser
import sys

from pyramid import testing

_testing_settings_dict = None

def get_testing_settings():
    global _testing_settings_dict
    if _testing_settings_dict is None:
        _testing_settings_dict = {}
        try:
            config = configparser.ConfigParser()
            config.read_file(open('testing.ini'))
        except Exception as x:
            sys.stderr.write('Could not parse "testing.ini" file:\n')
            sys.stderr.write(str(x) + '\nUsing empty settings dict...\n')
        else:
            keys = ['phylesystem-api.host', 'phylesystem-api.prefix', 'otc.host', 'otc.port', 'otc.prefix']
            for k in keys:
                try:
                    setting = config.get('app:main', k)
                    if setting:
                        _testing_settings_dict[k] = setting
                except:
                    sys.stderr.write('did not read a setting for "{}" using default...\n')
    return dict(_testing_settings_dict)

class ViewTests(unittest.TestCase):
    def setUp(self):
        self.config = testing.setUp()

    def tearDown(self):
        testing.tearDown()

    # def test_my_view(self):
    #     from .views import my_view
    #     request = testing.DummyRequest()
    #     info = my_view(request)
    #     self.assertEqual(info['project'], 'OpenTree Web-Services Wrapper')


class FunctionalTests(unittest.TestCase):
    def setUp(self):
        from ws_wrapper import main
        app = main({}, **get_testing_settings())
        from webtest import TestApp
        self.testapp = TestApp(app)

    def test_root(self):
        res = self.testapp.get('/', status=200)



