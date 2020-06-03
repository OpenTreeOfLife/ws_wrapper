from pyramid.response import Response
from pyramid.view import view_config
from ws_wrapper.exceptions import HttpResponseError
from cachetools import cached, LFUCache
from cachetools.keys import hashkey
from threading import RLock

# Set up a cache to store up to 512 responses
response_cache = LFUCache(maxsize=512, getsizeof=lambda v: 1)
cache_lock = RLock()

try:
    # Python 3
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen


    def encode_request_data(ds):
        if isinstance(ds, str):
            return ds.encode('utf-8')
        return ds


    from urllib.error import HTTPError, URLError
except ImportError:
    # python 2.7
    # noinspection PyUnresolvedReferences
    from urllib import urlencode
    # noinspection PyCompatibility,PyUnresolvedReferences
    from urllib2 import HTTPError, URLError, Request, urlopen


    def encode_request_data(ds):
        return ds

from peyotl.utility.str_util import is_int_type, is_str_type
import json
import re

# noinspection PyPackageRequirements
from peyotl.nexson_syntax import PhyloSchema

import logging

log = logging.getLogger('ws_wrapper')


# Do we want to strip the outgroup? If we do, it matches propinquity.
def get_newick_tree_from_study(study_nexson, tree):
    ps = PhyloSchema('newick',
                     content='subtree',
                     content_id=(tree, 'ingroup'),
                     otu_label='_nodeid_ottid')
    newick = ps.serialize(study_nexson)

    # Try again if there is no ingroup!
    if not newick:
        log.debug('Attempting to get newick but got "{}"!'.format(newick))
        log.debug('Retrying newick parsing without reference to an ingroup.')
        ps = PhyloSchema('newick',
                         content='subtree',
                         content_id=(tree, None),
                         otu_label='_nodeid_ottid')
        newick = ps.serialize(study_nexson)

    if not newick:
        log.debug('Second attempt to get newick failed.')
        raise HttpResponseError("Failed to extract newick tree from nexson!", 500)
    return newick


# EXCEPTION VIEW. This is how we are supposed to deal with exceptions.
# See https://docs.pylonsproject.org/projects/pyramid/en/1.6-branch/narr/views.html#custom-exception-views
# noinspection PyUnusedLocal
@view_config(context=HttpResponseError)
def generic_exception_catcher(exc, request):
    return Response(exc.body, exc.code, headers={'Content-Type': 'application/json'})


def get_json_or_none(body):
    # Don't give an unexplained internal server error if the JSON is malformed.
    try:
        j = json.loads(body)
        return j
    except ValueError:
        return None


def get_json(body):
    # Note that otc-tol-ws treats '' as '{}'.
    # That should probably be replicated here (or changed in otc-tol-ws),
    #   except that we currently avoid transforming badly formed JSON, and hand it
    #   to otc-tol-ws unmodified.

    j = get_json_or_none(body)
    if not j:
        raise HttpResponseError("Could not get JSON from body {}".format(body), 400)
    return j


def try_convert_to_integer(o):
    if is_str_type(o):
        try:
            return int(o)
        except TypeError:
            pass
    return o


def _merge_ott_and_node_id(body, as_dict=False, raise_if_lacking_both=True):
    # If the JSON doesn't parse, get out of the way and let otc-tol-ws handle the errors.
    j_args = get_json_or_none(body)
    if not j_args:
        if raise_if_lacking_both:
            raise HttpResponseError(body='Expecting at least one of: "node_id", or "ott_id"', code=400)
        return j_args if as_dict else body
    # Only modify the JSON if there is something to do.
    if 'ott_id' not in j_args:
        ni = j_args.get('node_id')
        if ni is None:
            if raise_if_lacking_both:
                raise HttpResponseError(body='Expecting at least one of: "node_id", or "ott_id"', code=400)
            return j_args if as_dict else body
        if not isinstance(ni, str):
            m = 'Expecting at least "node_id" to be a string, found {}'
            raise HttpResponseError(body=m.format(type(ni)), code=400)
        return j_args if as_dict else body
    # Only modify the JSON if there is something to do.
    if 'node_id' in j_args:
        raise HttpResponseError(body='Expecting only one of node_id or ott_id arguments', code=400)
    ott_id = j_args.pop('ott_id')
    # Convert string to integer... to handle old peyotl
    ott_id = try_convert_to_integer(ott_id)
    if not is_int_type(ott_id):
        m = 'Expecting "ott_id" to be an integer, but got "{}"'.format(ott_id)
        raise HttpResponseError(body=m, code=400)
    j_args['node_id'] = "ott{}".format(ott_id)
    return j_args if as_dict else json.dumps(j_args)

def _merge_ott_and_node_id_to_node_ids(body, as_dict=False):
    to_node_id = _merge_ott_and_node_id(body=body, as_dict=True, raise_if_lacking_both=False)
    node_ids = to_node_id.get('node_ids')
    if node_ids is None:
        return to_node_id if as_dict else json.dumps(to_node_id)
    if not isinstance(node_ids, list):
        raise HttpResponseError(body='"node_ids" to be a list: found "{}"'.format(node_ids), code=400)
    sing_node_id = to_node_id.get('node_id', None)
    if sing_node_id is None:
        if not node_ids:
            raise HttpResponseError(body='Expecting at least one of: "node_ids", "node_id", or "ott_id"', code=400)
    else:
        if not isinstance(sing_node_id, str):
            raise HttpResponseError(body='"node_id" to be a string: found "{}"'.format(sing_node_id), code=400)
    return to_node_id if as_dict else json.dumps(to_node_id)


def _merge_ott_and_node_ids(body):
    # If the JSON doesn't parse, get out of the way and let otc-tol-ws handle the errors.
    j_args = get_json_or_none(body)
    if not j_args:
        return body

    # Only modify the JSON if there is something to do.
    if 'ott_ids' not in j_args:
        return body

    node_ids = j_args.pop('node_ids', [])
    log.debug('node_ids = "{}"'.format(node_ids))
    # Handle "node_ids": null
    if node_ids is None:
        node_ids = []

    if not isinstance(node_ids, list):
        raise HttpResponseError(body='Expecting "node_ids" argument to be an array', code=400)

    ott_ids = j_args.pop('ott_ids', [])
    if ott_ids is None:
        ott_ids = []

    if not isinstance(ott_ids, list):
        raise HttpResponseError(body='Expecting "ott_ids" argument to be an array', code=400)

    # Append the ott_ids after the node_ids
    for o in ott_ids:
        # Convert string to integer... to handle old peyotl
        o = try_convert_to_integer(o)
        if not is_int_type(o):
            raise HttpResponseError(
                body='Expecting each element of "ott_ids" to be an integer, but got element "{}"'.format(
                    o), code=400)
        node_ids.append("ott{}".format(o))
        j_args['node_ids'] = node_ids

    return json.dumps(j_args)


_DEF_HEADER = {'Content-Type': 'application/json'}


# This method needs to return a Response object (See `from pyramid.response import Response`)
def _http_request_or_excep(method, url, data=None, headers=None, data_cache_hasher=None):
    """calls _cached_http_request_or_excep if data_cache_hasher is not None, and the
    response from calling it with the `data` argument is not None.
    """
    data_str = data
    try:
        if isinstance(data, dict):
            data_str = json.dumps(data)
    except Exception:
        log.warning('could not encode dict json: {}'.format(repr(data)))
    if data_cache_hasher is not None:
        try:
            hdk = data_cache_hasher(data)
        except Exception as x:
            log.exception('Could not hash "{}"'.format(data))
        else:
            if hdk is not None:
                mud_tuple = (method, url, hdk,)
                x = _cached_http_request_or_excep(mud_tuple, data_str, headers)
                with cache_lock:
                    y = response_cache.currsize
                log.debug('Curr cache size = {}'.format(y))
                return x
    return _uncached_http_request_or_excep(method, url, data_str, headers)


# noinspection PyUnusedLocal
def hash_first(mud_tuple, data, headers):
    return hashkey(mud_tuple)


# Cache, but not based on the headers (which are a dict)
# @TODO Are there any headers we need to cache control on?
@cached(cache=response_cache, key=hash_first, lock=cache_lock)
def _cached_http_request_or_excep(mud_tuple, data, headers):
    method, url = mud_tuple[0:2]
    x = _uncached_http_request_or_excep(method, url, data, headers)
    # remove non-cacheable headers (data, no-cache pragma)
    h = x.headers
    pv = h.get('Pragma')
    if pv:
        if pv == 'no-cache':
            del h['Pragma']
    for td in ['Cache-Control', 'Date', 'Expires']:
        if td in h:
            del h[td]
    # print('_cached_http_request_or_excep headers = {}'.format(x.headers))
    return x


def _uncached_http_request_or_excep(method, url, data, headers):
    log.debug('   Performing {} request: URL={}'.format(method, url))
    if headers is None:
        headers = _DEF_HEADER
    else:
        headers['Content-Type'] = 'application/json'
    req = Request(url=url, data=encode_request_data(data), headers=headers)
    req.get_method = lambda: method
    try:
        # this raises an exception if resp.code isn't 200, which is ridiculous
        resp = urlopen(req)
        headerobj = resp.info()
        return Response(resp.read(), resp.code, headers=headerobj)
    except HTTPError as err:
        try:
            return Response(err.read(), err.code, headers=err.info())
        except:
            raise HttpResponseError(err.reason, err.code)
    except URLError as err:
        raise HttpResponseError("Error: could not connect to '{}'".format(url), 500)


# ROUTE VIEWS
class WSView:
    # noinspection PyUnresolvedReferences
    def __init__(self, request):
        self.request = request
        settings = self.request.registry.settings
        self.study_host = settings.get('phylesystem-api.host', 'https://api.opentreeoflife.org')
        self.study_port = settings.get('phylesystem-api.port', '')
        if self.study_port:
            self.study_url_pref = '{}:{}'.format(self.study_host, self.study_port)
        else:
            self.study_url_pref = self.study_host
        self.study_path_prefix = settings.get('phylesystem-api.prefix', '')
        self.study_prefix = '{}/{}'.format(self.study_url_pref, self.study_path_prefix)
        self.otc_host = settings.get('otc.host', 'http://localhost')
        self.otc_port = settings.get('otc.port', '1984')
        self.otc_path_prefix = settings.get('otc.prefix', 'v3')
        if self.otc_port:
            self.otc_url_pref = '{}:{}'.format(self.otc_host, self.otc_port)
        else:
            self.otc_url_pref = self.otc_host
        self.otc_prefix = '{}/{}'.format(self.otc_url_pref, self.otc_path_prefix)

    def _forward_post(self, fullpath, data=None, headers=None, data_cache_hasher=None):
        # log.debug('Forwarding request: URL={}'.format(fullpath))
        method = self.request.method
        if method == 'GET':
            method = 'POST'
        if method == 'OPTIONS' or method == 'POST':
            r = _http_request_or_excep(method, fullpath, data=data, headers=headers, data_cache_hasher=data_cache_hasher)
            log.debug('   Returning response "{}"'.format(r.status_code))
            return r
        else:
            msg = "Refusing to forward method '{}': only forwarding POST and OPTIONS!"
            raise HttpResponseError(msg.format(method), 400)

    def forward_post_to_otc(self, path, data=None, headers=None, data_cache_hasher=None):
        """delegate to otcetera-based server. if data_cache_hasher is not None, the response will be cached basec
        on the url, method, and cached value of the data"""
        fullpath = self.otc_prefix + path
        r = self._forward_post(fullpath, data=data, headers=headers, data_cache_hasher=data_cache_hasher)
        r.headers.pop('Connection', None)
        return r


    def phylesystem_get(self, path):
        url = self.study_prefix + path
        log.debug("Fetching study from phylesystem: PATH={}".format(path))
        r = _http_request_or_excep("GET", url)
        log.debug("Fetching study from phylesystem: SUCCESS!")
        return r

    def phylesystem_get_json(self, path):
        r = self.phylesystem_get(path)
        j = json.loads(r.body)
        if 'data' not in j.keys():
            raise HttpResponseError("Error accessing phylesystem: no 'data' element in reply!", 500)
        return j['data']

    def get_study_nexson(self, study):
        return self.phylesystem_get_json('/study/' + study)

    def get_study_tree(self, study, tree):
        study_nexson = self.get_study_nexson(study)
        return get_newick_tree_from_study(study_nexson, tree)

    @view_config(route_name='home')
    def home_view(self):
        return Response('<body>This is home</body>')

    @view_config(route_name='tol:about')
    def tol_about_view(self):
        j = None
        if self.request.body:
            j = get_json(self.request.body)
            if j:
                if 'include_source_list' not in j:
                    m = '"include_source_list" is the only argument allowed for tree_of_life/about call. Found {}'
                    raise HttpResponseError(m.format(j.keys()), 400)
        return self.forward_post_to_otc("/tree_of_life/about", data=j, data_cache_hasher=_tol_about_data_cache_hasher)

    @view_config(route_name='tol:node_info')
    def tol_node_info_view(self):
        d = _merge_ott_and_node_id_to_node_ids(self.request.body, as_dict=True)
        d.setdefault('include_lineage', False)
        if len(d) != 2:
            m = 'Expecting only "include_lineage" and a node specifier for a tree_of_life/node_info call. Found {}'
            raise HttpResponseError(m.format(d.keys()), 400)
        return self.forward_post_to_otc("/tree_of_life/node_info", data=d, data_cache_hasher=_tol_node_info_cache_hasher)

    @view_config(route_name='tol:mrca')
    def tol_mrca_view(self):
        d = _merge_ott_and_node_ids(self.request.body)
        return self.forward_post_to_otc("/tree_of_life/mrca", data=d)

    @view_config(route_name='tol:subtree')
    def tol_subtree_view(self):
        d = _merge_ott_and_node_id(self.request.body)
        fmt = d.get('format')
        if fmt is None:
            d['format'] = 'newick'
        else:
            try:
                lc = fmt.lower()
                assert lc == 'newick' or lc == 'arguson'
            except:
                raise HttpResponseError('Expecting format to be either "newick" or "arguson"', 400)
            if lc != fmt:
                d['format'] = lc # make this case-insensitive? I guess so...
            hl = d.get('height_limit')
            if (hl is not None) and not is_int_type(hl):
                raise HttpResponseError('Expecting "height_limit" to be an integer', 400)
            if lc == 'newick':
                lf = d.setdefault('label_format', 'name_and_id')
                if lf not in _valid_subtree_newick_label_formats:
                    raise HttpResponseError('Illegal value for "label_format" = {}'.format(lf), 400)
        return self.forward_post_to_otc("/tree_of_life/subtree", data=d, data_cache_hasher=_tol_subtree_cache_hasher)

    @view_config(route_name='tol:induced_subtree')
    def tol_induced_subtree_view(self):
        d = _merge_ott_and_node_ids(self.request.body)
        return self.forward_post_to_otc("/tree_of_life/induced_subtree", data=d)

    @view_config(route_name='tax:about')
    def tax_about_view(self):
        return self.forward_post_to_otc("/taxonomy/about", data=self.request.body)

    @view_config(route_name='tax:taxon_info')
    def tax_taxon_info_view(self):
        return self.forward_post_to_otc("/taxonomy/taxon_info", data=self.request.body)

    @view_config(route_name='tax:mrca')
    def tax_flags_view(self):
        return self.forward_post_to_otc("/taxonomy/mrca", data=self.request.body)

    @view_config(route_name='tax:flags')
    def tax_mrca_view(self):
        return self.forward_post_to_otc("/taxonomy/flags", data=self.request.body)

    @view_config(route_name='tax:subtree')
    def tax_subtree_view(self):
        return self.forward_post_to_otc("/taxonomy/subtree", data=self.request.body)

    @view_config(route_name='tnrs:match_names')
    def tnrs_match_names_view(self):
        return self.forward_post_to_otc("/tnrs/match_names", data=self.request.body)

    @view_config(route_name='tnrs:autocomplete_name')
    def tnrs_autocomplete_name_view(self):
        return self.forward_post_to_otc("/tnrs/autocomplete_name", data=self.request.body)

    @view_config(route_name='tnrs:contexts')
    def tnrs_contexts_view(self):
        return self.forward_post_to_otc("/tnrs/contexts", data=self.request.body)

    @view_config(route_name='tnrs:infer_context')
    def tnrs_infer_context_view(self):
        return self.forward_post_to_otc("/tnrs/infer_context", data=self.request.body)

    @view_config(route_name='conflict:conflict-status')
    def conflict_status_view(self):
        if self.request.method == "GET":
            if 'tree1' in self.request.GET and 'tree2' in self.request.GET:
                j = {u'tree1': self.request.GET['tree1'], u'tree2': self.request.GET['tree2']}
                self.request.method = 'POST'
            else:
                log.debug("self.request.GET={}".format(self.request.GET))
                raise HttpResponseError(
                    "ws_wrapper:conflict-status [translating GET->POST]:\n  Expecting arguments 'tree1' and 'tree2', but got:\n{}\n".format(
                        self.request.GET), 400)
        else:
            j = get_json(self.request.body)
        if 'tree1' in j.keys():
            study1, tree1 = re.split('[@#]', j['tree1'])
            j.pop('tree1', None)
            j[u'tree1newick'] = self.get_study_tree(study1, tree1)
        return self.forward_post_to_otc('/conflict/conflict-status', data=json.dumps(j))


def _tol_about_data_cache_hasher(x):
    return False if not x else x.get('include_source_list', False)

def _tol_node_info_cache_hasher(x):
    ilv = x.get('include_lineage', False)
    nil = x.get('node_ids')
    if nil is not None:
        if not isinstance(nil, list):
            raise HttpResponseError('Server Error extracting node_ids as list. Please report this bug', 500)
        nil = tuple(nil)
    else:
        try:
            nil = x['node_id']
            assert is_str_type(nil)
        except:
            raise HttpResponseError('Server Error extracting node_id as string. Please report this bug', 500)
    return hashkey(ilv, nil)

def _tol_subtree_cache_hasher(x):
    node_id = x.get('node_id')
    assert node_id
    fmt = x.get('format')
    assert fmt == 'newick' or fmt == 'arguson'

_valid_subtree_newick_label_formats = frozenset(["name", "id", "name_and_id"])

