import logging
log = logging.getLogger('ws_wrapper')

class HttpResponseError(Exception):
    def __init__(self, body, code):
        log.warn(body)
        self.body = body
        self.code = code
