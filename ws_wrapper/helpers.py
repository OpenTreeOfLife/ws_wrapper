#!/usr/bin/env python

_AMENDMENT_REPO_URL_TEMPLATE = 'https://github.com/OpenTreeOfLife/amendments-1/blob/master/amendments/{}.json'

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
