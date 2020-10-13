#!/usr/bin/env python3
from peyotl.utility.str_util import is_str_type, is_int_type


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
