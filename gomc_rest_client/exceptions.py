class GomcRestError(Exception):
    """Base exception for all gomc_rest_client errors.

    Attributes:
        message: Human-readable description of the error.
        status: HTTP status code returned by the server (0 if no response).
        code: Machine-readable error code string returned by the server.

    Example:
        >>> try:
        ...     plc.read("D100", 1)
        ... except GomcRestError as exc:
        ...     print(exc.status, exc.code, exc.message)
    """

    def __init__(self, message: str, status: int, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


class GomcRestBadRequestError(GomcRestError):
    """Raised when the server returns HTTP 400 Bad Request.

    This typically means an invalid address, out-of-range count, or other
    malformed request parameter was sent.
    """


class GomcRestForbiddenError(GomcRestError):
    """Raised when the server returns HTTP 403 Forbidden.

    Remote-control endpoints (``/remote/*``) require the server to be started
    with the ``-enable-remote`` flag. Calling them without that flag raises
    this error.
    """


class GomcRestPLCProtocolError(GomcRestError):
    """Raised when the PLC itself returns a protocol-level error.

    Attributes:
        end_code: The end code string returned by the PLC (e.g. ``"C059"``).

    Example:
        >>> try:
        ...     plc.read("D100", 1)
        ... except GomcRestPLCProtocolError as exc:
        ...     print(f"PLC error {exc.end_code}: {exc.message}")
    """

    def __init__(self, message: str, status: int, code: str, end_code: str) -> None:
        super().__init__(message, status, code)
        self.end_code = end_code


class GomcRestConnectionError(GomcRestError):
    """Raised when a network-level connection to the gomc-rest server fails.

    Common causes include the server not running, a wrong host/port, or a
    firewall blocking the connection.
    """


class GomcRestBusyError(GomcRestError):
    """Raised when the gomc-rest server is temporarily busy.

    The server serialises PLC requests through an internal queue. This error
    occurs when that queue is full and the request could not be accepted.
    Retrying after a short delay is usually sufficient.
    """


class GomcRestQueueClosedError(GomcRestError):
    """Raised when the gomc-rest server's internal request queue has been closed.

    This usually means the server is shutting down.
    """


class GomcRestRequestCanceledError(GomcRestError):
    """Raised when the gomc-rest server canceled the request before completion."""


class GomcRestRequestTimeoutError(GomcRestError):
    """Raised when the request to the gomc-rest server timed out.

    The timeout threshold is controlled by the ``timeout`` parameter of
    :class:`PLCClient`.
    """
