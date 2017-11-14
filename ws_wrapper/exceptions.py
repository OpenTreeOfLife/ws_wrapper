from pyramid.view import view_config

class HttpResponseError(Exception):
    def __init__(self,body,code):
        self.body = body
        self.code = code
