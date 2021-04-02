#!/usr/bin/env python3
from peyutil import is_str_type, is_int_type
from threading import RLock
import requests
import logging

log = logging.getLogger('ws_wrapper.util')

def convert_arg_to_ott_int(o):
    if is_str_type(o):
        if o.startswith('ott'):
            return int(o[3:].strip())
        try:
            return int(o.strip())
        except TypeError:
            pass
    elif is_int_type(o):
        return o
    return None

class SetFromWSCache(object):
    """Wrapper around a set that allows for check with the `in` operator.

    If an item is not found, the cache is refreshed by calling `fetch_fn`
    which is (presumably) an expensive web-service call, then the check
    is repeated.
    """
    def __init__(self, fetch_fn, initial=None):
        """Initial can be an iterable of items. `fetch_fn` should be a callable (no args) that returns an
        iterable of items.
        """
        self._lock = RLock()
        self._cache = set()
        self._fetch_fn = fetch_fn
        if initial:
            self._cache.update(initial)

    def first_item_in(self, item_list):
        """Returns None (if not found) or first item in `item_list` that is in the set."""
        with self._lock:
            for item in item_list:
                if item in self._cache:
                    return item
        ref = self._fetch_fn()
        if not ref:
            return None
        with self._lock:
            self._cache.update(ref)
        for item in item_list:
            if item in ref:
                return item

    def __contains__(self, item):
        with self._lock:
            if item in self._cache:
                return True
        ref = self._fetch_fn()
        if not ref:
            return False
        with self._lock:
            self._cache.update(ref)
            return item in self._cache

_coll_name_checker = None
def get_collection_name_checker(settings_dict):
    """Returns a reference to a SetFromWSCache that acts as a collection ID checker (Singelton, lozy initialization)."""
    global _coll_name_checker
    if _coll_name_checker is not None:
        return _coll_name_checker
    ps_host = settings_dict.get('phylesystem-api.host', 'https://api.opentreeoflife.org')
    ps_vnum = settings_dict.get('phylesystem-api.prefix', 'v3')
    coll_list_url = '{h}/{v}/collections/collection_list'.format(h=ps_host, v=ps_vnum)

    def fetch_new_collection_names():
        """Uses requests to get the list of collection names. Logs errors and returns an empty list on failures."""
        resp = requests.get(coll_list_url, headers={'content-type': 'application/json', 'accept': 'application/json'})
        try:
            resp.raise_for_status()
            rj = resp.json()
            assert isinstance(rj, list)
            rs = set(rj)
            return rs
        except Exception as x:
            log.error('Call to {} to fetch collection IDs failed: {}'.format(coll_list_url, str(x)))
            return []

    _coll_name_checker = SetFromWSCache(fetch_fn=fetch_new_collection_names)
    return _coll_name_checker
