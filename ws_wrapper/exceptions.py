import logging
import json

log = logging.getLogger('ws_wrapper')

# See ws_wrapper/views.py for an exception view that converts this to
# an http Response( ) with headers.

class HttpResponseError(Exception):
    def __init__(self, body, code):
        log.warn(body + "\n")
        e = dict()
        e["message"] = body
        self.body = json.dumps(e, indent=4) + "\n"
        self.code = code
