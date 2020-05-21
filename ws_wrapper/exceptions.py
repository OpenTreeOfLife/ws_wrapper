import logging
import json

log = logging.getLogger('ws_wrapper')


class HttpResponseError(Exception):
    def __init__(self, body, code):
        log.warning(body + "\n")
        e = dict()
        e["message"] = body
        self.body = json.dumps(e, indent=4) + "\n"
        self.code = code
