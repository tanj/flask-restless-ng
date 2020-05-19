class APIError(Exception):
    """This is a base class for all API related exceptions"""
    status_code = 500

    def __init__(self, detail, status_code=None, cause=None):
        super().__init__()
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code
        self.cause = cause


class NotFound(APIError):
    """Exception thrown when a requested resource was not found"""
    status_code = 404
