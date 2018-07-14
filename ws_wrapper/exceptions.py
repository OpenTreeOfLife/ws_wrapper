class HttpResponseError(Exception):
    def __init__(self, body, code):
        self.body = body
        self.code = code
