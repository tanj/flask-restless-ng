from http.client import BAD_REQUEST
from http.client import NOT_FOUND


class Error(Exception):
    http_code = 500

    def __init__(self, cause=None, details=None):
        self.cause = cause
        self.details = details


class BadRequest(Error):
    http_code = BAD_REQUEST


class NotFound(Error):
    http_code = NOT_FOUND
