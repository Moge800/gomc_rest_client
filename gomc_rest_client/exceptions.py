class GomcRestError(Exception):
    """Base for all gomc_rest_client errors."""

    def __init__(self, message: str, status: int, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


class GomcRestBadRequestError(GomcRestError):
    pass


class GomcRestForbiddenError(GomcRestError):
    pass


class GomcRestPLCProtocolError(GomcRestError):
    def __init__(self, message: str, status: int, code: str, end_code: str) -> None:
        super().__init__(message, status, code)
        self.end_code = end_code


class GomcRestConnectionError(GomcRestError):
    pass


class GomcRestBusyError(GomcRestError):
    pass


class GomcRestQueueClosedError(GomcRestError):
    pass


class GomcRestRequestCanceledError(GomcRestError):
    pass


class GomcRestRequestTimeoutError(GomcRestError):
    pass


PLCError = GomcRestError
BadRequestError = GomcRestBadRequestError
ForbiddenError = GomcRestForbiddenError
PLCProtocolError = GomcRestPLCProtocolError
ConnectionError = GomcRestConnectionError
BusyError = GomcRestBusyError
QueueClosedError = GomcRestQueueClosedError
RequestCanceledError = GomcRestRequestCanceledError
RequestTimeoutError = GomcRestRequestTimeoutError
