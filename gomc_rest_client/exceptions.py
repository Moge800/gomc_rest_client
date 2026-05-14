class PLCError(Exception):
    """Base for all gomc_rest_client errors."""

    def __init__(self, message: str, status: int, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


class BadRequestError(PLCError):
    pass


class ForbiddenError(PLCError):
    pass


class PLCProtocolError(PLCError):
    def __init__(self, message: str, status: int, code: str, end_code: str) -> None:
        super().__init__(message, status, code)
        self.end_code = end_code


class ConnectionError(PLCError):
    pass


class BusyError(PLCError):
    pass


class QueueClosedError(PLCError):
    pass


class RequestCanceledError(PLCError):
    pass


class RequestTimeoutError(PLCError):
    pass