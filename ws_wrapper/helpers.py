#!/usr/bin/env python
import logging
_AMENDMENT_REPO_URL_TEMPLATE = 'https://github.com/OpenTreeOfLife/amendments-1/blob/master/amendments/{}.json'


def _config_setting_to_att(s):
    no_dot = s.replace('.', '_')
    return no_dot.replace('-', '_')

def _config_get(log, settings, att, config_var, default):
    if config_var not in settings:
        m = '  {} = {} (default, because "{}" not in config settings)'
        log.info(m.format(att, repr(default), config_var))
        return default
    val = settings[config_var]
    m = '  {} = {} (based on "{}" in config settings)'
    log.info(m.format(att, repr(val), config_var))
    return val

class ConstSettings(object):
    """Parsed version of the settings dict. Singleton created in `main` from __init__.py."""
    def __init__(self, settings):
        self.serve_phylesystem = None
        self.serve_otc = None
        self.serve_taxonomy_browse = None
        self.study_prefix = None
        self.otc_prefix = None

        log = logging.getLogger('ws_wrapper')
        service_list = ('phylesystem', 'otc', 'taxonomy-browse')
        for svc in service_list:
            s = 'serve.{}'.format(svc)
            if s not in settings:
                log.info('  "{}" not found defaulting to False'.format(s))
                val = False
            else:
                sval = settings[s]
                val = sval.lower() == 'true'
                if not val:
                    log.info('  {} = "{}" not equivalent to "true" defaulting to False'.format(s, sval))
            att = _config_setting_to_att(s)
            setattr(self, att, val)
            log.info('cfg_dep.{}: {}  (based on "{}" in config settings)'.format(att, val, s))

        cfg_for_service = (('study', 'phylesystem-api', 'https://api.opentreeoflife.org', None, ''),
                           ('otc', 'otc', 'http://localhost', '1984',  'v3'),
                           ('tree_browser', 'treebrowser', 'https://tree.opentreeoflife.org', None, ''), )
        for tup in cfg_for_service:
            self._set_svc_prefix(log, settings, tup)

    def _set_svc_prefix(self, log, settings, tup):
        att_name, cfg_name, host_def, port_def, pref_def = tup
        ahn = '{}_host'.format(att_name)
        chn = '{}.host'.format(cfg_name)
        apn = '{}_port'.format(att_name)
        cpn = '{}.port'.format(cfg_name)
        # TODO: should probably not call the config var for the path part "*.prefix"
        #   and then use *_prefix (obj_att being set here) in the code for the full URL.
        #   Fix this when we have moved from germinator so that deployment only has to change once.
        appn = '{}_path_prefix'.format(att_name)
        cppn = '{}.prefix'.format(cfg_name)
        att_host = _config_get(log, settings, ahn, chn, host_def)
        att_port = _config_get(log, settings, apn, cpn, port_def)
        att_path_prefix = _config_get(log, settings, appn, cppn, pref_def)
        if att_port:
            att_url_pref = '{}:{}'.format(att_host, att_port)
        else:
            att_url_pref = att_host
        obj_att = '{}_prefix'.format(att_name)
        att_val = '{}/{}'.format(att_url_pref, att_path_prefix)
        setattr(self, obj_att, att_val)
        m = 'cfg_dep.{} = {} (based on {}, {}, {})'
        log.info(m.format(obj_att, repr(att_val), ahn, apn, appn))
        return att_val




def taxon_source_id_to_url_and_name(source_id):
    link_name = source_id
    if source_id.startswith('http:') or source_id.startswith('https:'):
        url = source_id
    else:
        parts = source_id.split(':')
        url = None
        if len(parts) == 2:
            if parts[0] == 'ncbi':
                url = 'http://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id=%s' % parts[1]
            elif parts[0] == 'gbif':
                url = 'http://www.gbif.org/species/%s/' % parts[1]
            elif parts[0] == 'irmng':
                # url = 'http://www.marine.csiro.au/mirrorsearch/ir_search.taxon_info?id=%s' % parts[1]
                url = 'http://www.irmng.org/aphia.php?p=taxdetails&id=%s' % parts[1]
            elif parts[0] == 'if':
                url = 'http://www.indexfungorum.org/names/NamesRecord.asp?RecordID=%s' % parts[1]
            elif parts[0] == 'worms':
                url = 'http://www.marinespecies.org/aphia.php?p=taxdetails&id=%s' % parts[1]
            elif parts[0] == 'silva':
                url = 'http://www.arb-silva.de/browser/ssu/silva/%s' % parts[1]
            else:
                # check for taxonomic amendments; link each directly to its latest version on GitHub
                possible_amendment_id = parts[0]  # EXAMPLE source_id: 'additions-10000038-10000038:10000038'
                id_parts = possible_amendment_id.split('-')
                # see peyotl for amendment types and prefixes
                # https://github.com/OpenTreeOfLife/peyotl/blob/3c32582e16be9dcf1029ce3d6481cdb09444890a/peyotl/amendments/amendments_umbrella.py#L33-L34
                if (len(id_parts) > 1) and id_parts[0] in ('additions', 'changes', 'deletions',):
                    url = _AMENDMENT_REPO_URL_TEMPLATE.format(possible_amendment_id)
                    # we use a special displayed format for amendments
                    type_to_singular_prefix = {'additions':'addition' , 'changes':'change', 'deletions':'deletion'}
                    prefix = type_to_singular_prefix.get(id_parts[0])
                    node_id = parts[1]
                    formatted_id = '%s:%s' % (prefix, node_id)
                    link_name = formatted_id
    return url, link_name
