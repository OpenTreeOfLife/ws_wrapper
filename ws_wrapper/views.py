from pyramid.response import Response
from pyramid.view import view_config
from ws_wrapper.exceptions import HttpResponseError
from pyramid.renderers import render_to_response

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
    from urllib import urlencode
    # noinspection PyCompatibility
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


def _merge_ott_and_node_id(body):
    # If the JSON doesn't parse, get out of the way and let otc-tol-ws handle the errors.
    j_args = get_json_or_none(body)
    if not j_args:
        return body
    # Only modify the JSON if there is something to do.
    if 'ott_id' not in j_args:
        return body
    # Only modify the JSON if there is something to do.
    if 'node_id' in j_args:
        raise HttpResponseError(body='Expecting only one of node_id or ott_id arguments', code=400)
    ott_id = j_args.pop('ott_id')
    # Convert string to integer... to handle old peyotl
    ott_id = try_convert_to_integer(ott_id)
    if not is_int_type(ott_id):
        raise HttpResponseError(
            body='Expecting "ott_id" to be an integer, but got "{}"'.format(ott_id), code=400)
    j_args['node_id'] = "ott{}".format(ott_id)

    return json.dumps(j_args)


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

# This method needs to return a Response object (See `from pyramid.response import Response`)
def _http_request_or_excep(method, url, data=None, headers={}):
    log.debug('   Performing {} request: URL={}'.format(method, url))
    try:
        if isinstance(data, dict):
            data = json.dumps(data)
    except Exception:
        log.warn('could not encode dict json: {}'.format(repr(data)))

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

OTT_VERSION = None
SYNTH_ABOUT_BLOB = None

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
        self.tree_browser_prefix = settings.get('treebrowser.host',
                                                'https://tree.opentreeoflife.org')

    def _forward_post(self, fullpath, data=None, headers={}):
        log.debug('Forwarding request: URL={}'.format(fullpath))
        method = self.request.method
        if method == 'GET':
            method = 'POST'
        if method == 'POST' or method == 'OPTIONS':
            r = _http_request_or_excep(method, fullpath, data=data, headers=headers)
#            log.debug('   Returning response "{}"'.format(r))
            return r
        else:
            msg = "Refusing to forward method '{}': only forwarding POST and OPTIONS!"
            raise HttpResponseError(msg.format(method), 400)

    def forward_post_to_otc(self, path, data=None, headers={}):
        fullpath = self.otc_prefix + path
        r = self._forward_post(fullpath, data=data, headers=headers)
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
        return self.forward_post_to_otc("/tree_of_life/about", data=self.request.body)

    @view_config(route_name='tol:node_info')
    def tol_node_info_view(self):
        d = _merge_ott_and_node_id(self.request.body)
        return self.forward_post_to_otc("/tree_of_life/node_info", data=d)

    @view_config(route_name='tol:mrca')
    def tol_mrca_view(self):
        d = _merge_ott_and_node_ids(self.request.body)
        return self.forward_post_to_otc("/tree_of_life/mrca", data=d)

    @view_config(route_name='tol:subtree')
    def tol_subtree_view(self):
        d = _merge_ott_and_node_id(self.request.body)
        return self.forward_post_to_otc("/tree_of_life/subtree", data=d)

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
    def tnrs_match_names_view(self, data=None):
        d = self.request.body if data is None else data
        return self.forward_post_to_otc("/tnrs/match_names", data=d)

    @view_config(route_name='tnrs:autocomplete_name')
    def tnrs_autocomplete_name_view(self):
        return self.forward_post_to_otc("/tnrs/autocomplete_name", data=self.request.body)

    @view_config(route_name='tnrs:contexts')
    def tnrs_contexts_view(self):
        return self.forward_post_to_otc("/tnrs/contexts", data=self.request.body)

    @view_config(route_name='tnrs:infer_context')
    def tnrs_infer_context_view(self):
        return self.forward_post_to_otc("/tnrs/infer_context", data=self.request.body)

    def html_error_response(self, message, status=400):
        error_template = 'templates/genericerror.jinja2'
        return render_to_response(error_template,
                                  {'message': message},
                                  request=self.request,
                                  response=Response(status=status))

    @view_config(route_name='taxonomy:browse')
    def taxonomy_browse_view(self):
        request = self.request
        method = request.method
        if method != 'GET':
            msg = "Rejecting '{}': only GET is supported!"
            raise HttpResponseError(msg.format(method), 400)
        d = request.GET
        try:
            ott_id = d.getone('id')
        except KeyError:
            if d.getall('id'):
                return self.html_error_response("Only 1 id param can be sent")
        else:
            return self._taxon_browse_by_id(ott_id)
        try:
            name = d.getone('name')
        except KeyError:
            if d.getall('name'):
                return self.html_error_response("Only 1 name param can be sent")
            name = 'cellular organisms'
        try:
            ott_id = int(name)
        except:
            return self._taxon_browse_by_name(name)
        return self._taxon_browse_by_id(ott_id)

    def _taxon_browse_by_name(self, name):
        res_str = self.tnrs_match_names_view({'names': [name.strip()],
                                             'include_suppressed': True}).body
        matches = []
        try:
            res_blob = json.loads(res_str, encoding='utf-8')
            results = res_blob.get('results', [{}])
            matches = results[0].get('matches', [])
            assert len(matches) > 0
        except:
            return self.html_error_response("No TNRS match for \"{}\"".format(name))
        if len(matches) > 1:
            multi_match_template = 'templates/ambigname.jinja2'
            tparam = {'name': name, 'matches': matches}
            return render_to_response(multi_match_template, tparam, request=self.request)
        taxon = matches[0][u'taxon']
        ott_id = taxon[u'ott_id']
        return self._taxon_browse_by_id(ott_id)

    def _fetch_augmented_taxon_info(self, ott_id):
        from .helpers import taxon_source_id_to_url_and_name
        try:
            ott_id = int(ott_id)
        except:
            return self.html_error_response("Expecting OTT ID to be an integer found \"{}\"".format(ott_id))
        info = self._get_taxon_info_blob_or_response('ott_id', ott_id)
        if not isinstance(info, dict):
            return info
        info['display_name'] = get_display_name(info)
        info['ott_version'] = self.get_ott_version()
        rank = info.get('rank', 'no rank')
        info['rank_str'] = rank if not rank.startswith('no rank') else ''
        info['tax_source_links'] = [taxon_source_id_to_url_and_name(i) for i in info.get('tax_sources', [])]
        info['tree_browser'] = self.tree_browser_prefix
        info['synth_about'] = self.get_synth_about()
        sup_flags = frozenset(info['synth_about'].get('filtered_flags', []))
        unsuppressed_children, suppressed_children = [], []
        for child in info.get('children', []):
            if sup_flags.isdisjoint(child['flags']):
                unsuppressed_children.append(child)
            else:
                suppressed_children.append(child)
        info['unsuppressed_children'] = unsuppressed_children
        info['suppressed_children'] = suppressed_children

        return info

    def _taxon_browse_by_id(self, ott_id):
        success_template = 'templates/taxon.jinja2'
        info = self._fetch_augmented_taxon_info(ott_id)
        if not isinstance(info, dict):
            return info
        return render_to_response(success_template, info, request=self.request)

    def _get_taxon_info_blob_or_response(self, key, value):
        args = {key: value, 'include_children': True, 'include_lineage': True}
        resp = self.forward_post_to_otc("/taxonomy/taxon_info", data=args).body
        try:
            return  json.loads(resp, encoding='utf-8')
        except:
            return self.html_error_response("No taxon info for {}=\"{}\"".format(key, value))

    def _fetch_taxonomy_about(self):
        resp = self.forward_post_to_otc("/taxonomy/about").body
        try:
            return  json.loads(resp, encoding='utf-8')
        except:
            return self.html_error_response("Call to taxonomy/about method failed")

    def _fetch_synth_about_blob(self):
        resp = self.forward_post_to_otc("/tree_of_life/about").body
        try:
            return  json.loads(resp, encoding='utf-8')
        except:
            raise self.html_error_response("Call to taxonomy/about method failed")

    def _fetch_taxonomy_version(self):
        x = self._fetch_taxonomy_about()
        if not isinstance(x, dict):
            raise x
        try:
            version_info = x['source']
            return version_info.split('draft')[0]
        except:
            raise self.html_error_response('Problem parsing taxonomy/about response')

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


    def get_ott_version(self):
        global OTT_VERSION
        if OTT_VERSION is None:
            OTT_VERSION = self._fetch_taxonomy_version()
        return OTT_VERSION

    def get_synth_about(self):
        global SYNTH_ABOUT_BLOB
        if SYNTH_ABOUT_BLOB is None:
            SYNTH_ABOUT_BLOB = self._fetch_synth_about_blob()
        return SYNTH_ABOUT_BLOB
        
def get_display_name(taxon_info):
    un = taxon_info.get(u'unique_name')
    if un:
        return un
    return taxon_info.get(u'name', u'Unnamed taxon')

'''
# Sources
start_el(output, 'span', 'sources')
if u'tax_sources' in info:
    sources = info[u'tax_sources']
    if len(sources) > 0:
        output.write(' %s ' % source_link(sources[0]))
        if len(sources) > 1:
            output.write('(%s) ' % (', '.join(map(source_link, sources[1:])),))
end_el(output, 'span')

# Flags
start_el(output, 'span', 'flags')
output.write('%s ' % ', '.join(map(lambda f:'<span class="flag">%s</span>' % f.lower(), info[u'flags'])))
end_el(output, 'span')
output.write('\n')




    start_el(output, 'p', 'legend')
    version = get_taxonomy_version(api_base)
        display_basic_info(info, output)
        output.write(' (OTT id %s)' % id)
        synth_tree_url = "/opentree/argus/ottol@%s" % id
        output.write('<br/><a target="_blank" href="%s">View this taxon in the current synthetic tree</a>' % cgi.escape(synth_tree_url))

        end_el(output, 'p')

        if u'synonyms' in info:
            synonyms = info[u'synonyms']
            name = info[u'name']
            if name in synonyms:
                synonyms.remove(name)
            if len(synonyms) > 0:
                output.write('<h3>Synonym(s)</h3>')
                start_el(output, 'p', 'synonyms')
                output.write("%s\n" % ', '.join(map(link_to_name, synonyms)))
                end_el(output, 'p')
        if u'lineage' in info:
            first = True
            output.write('<h3>Lineage</h3>')
            start_el(output, 'p', 'lineage')
            # N.B. we reverse the list order to show the root first!
            if info[u'lineage']:
                info[u'lineage'].reverse()
            for ancestor in info[u'lineage']:
                if not first:
                    output.write(' &gt; ')
                output.write(link_to_taxon(ancestor[u'ott_id'], ancestor[u'name']))
                first = False
            output.write('\n')
            end_el(output, 'p')
        else:
            output.write('missing lineage field %s\n', info.keys())
        any_included = False
        any_suppressed = False
        if limit == None: limit = 200
        if u'children' in info:
            children = sorted(info[u'children'], key=priority)
            if len(children) > 0:

                # Generate initial output for two lists of children
                suppressed_children_output.write('<h3>Children suppressed from the synthetic tree</h3>')
                start_el(suppressed_children_output, 'ul', 'children')
                nth_suppressed_child = 0
                included_children_output.write('<h3>Children included in the synthetic tree</h3>')
                start_el(included_children_output, 'ul', 'children')
                nth_included_child = 0

                for child in children[:limit]:
                    if ishidden(child):
                        nth_suppressed_child += 1
                        odd_or_even = (nth_suppressed_child % 2) and 'odd' or 'even'
                        start_el(suppressed_children_output, 'li', 'child suppressed %s' % odd_or_even)
                        #write_suppressed(suppressed_children_output)
                        suppressed_children_output.write(' ')
                        display_basic_info(child, suppressed_children_output)
                        end_el(suppressed_children_output, 'li')
                        any_suppressed = True
                    else:
                        nth_included_child += 1
                        odd_or_even = (nth_included_child % 2) and 'odd' or 'even'
                        start_el(included_children_output, 'li', 'child exposed %s' % odd_or_even)
                        start_el(included_children_output, 'span', 'exposedmarker')
                        included_children_output.write("  ")
                        end_el(included_children_output, 'span')
                        included_children_output.write(' ')
                        display_basic_info(child, included_children_output)
                        end_el(included_children_output, 'li')
                        any_included = True

                end_el(suppressed_children_output, 'ul')
                end_el(included_children_output, 'ul')
        if any_included:
            output.write(included_children_output.getvalue())
        if any_suppressed:
            output.write(suppressed_children_output.getvalue())
        if u'children' in info:
            children = info[u'children']
            if children != None and len(children) > limit:
                start_el(output, 'p', 'more_children')
                output.write('... %s' % link_to_taxon(id,
                                                      ('%s more children' %
                                                       (len(children)-limit)),
                                                      limit=100000))
                end_el(output, 'p')
        output.write("\n")
    else:
        report_invalid_arg(output, info)
'''
