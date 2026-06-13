class GomcRestError(Exception):
    """Base exception for all gomc_rest_client errors.

    Attributes:
        message: Human-readable error description.
        status: HTTP status code (0 if no response was received).
        code: Machine-readable error code string from the server.
    """

    def __init__(self, message: str, status: int, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


class GomcRestBadRequestError(GomcRestError):
    """Raised on HTTP 400 — invalid address, out-of-range count, etc."""


class GomcRestForbiddenError(GomcRestError):
    """Raised on HTTP 403 — remote-control endpoints require ``-enable-remote``."""


class GomcRestPLCProtocolError(GomcRestError):
    """Raised when the PLC returns a protocol-level error.

    Attributes:
        end_code: PLC end code string (e.g. ``"C059"``).
    """

    def __init__(self, message: str, status: int, code: str, end_code: str) -> None:
        super().__init__(message, status, code)
        self.end_code = end_code


class GomcRestConnectionError(GomcRestError):
    """Raised when a network-level connection to the server fails."""


class GomcRestBusyError(GomcRestError):
    """Raised when the server's request queue is full. Retry after a short delay."""


class GomcRestQueueClosedError(GomcRestError):
    """Raised when the server's request queue has been closed (server shutting down)."""


class GomcRestRequestCanceledError(GomcRestError):
    """Raised when the server canceled the request before completion."""


class GomcRestRequestTimeoutError(GomcRestError):
    """Raised when the request timed out. Adjust ``PLCClient(timeout=...)`` if needed."""
