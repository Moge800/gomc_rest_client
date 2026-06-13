from __future__ import annotations

import json
import re
from http import client as http_client
from typing import Any, Protocol, TypedDict
from urllib import error, parse

from .exceptions import (
    GomcRestBadRequestError,
    GomcRestBusyError,
    GomcRestConnectionError,
    GomcRestError,
    GomcRestForbiddenError,
    GomcRestPLCProtocolError,
    GomcRestQueueClosedError,
    GomcRestRequestCanceledError,
    GomcRestRequestTimeoutError,
)

_CODE_TO_EXC = {
    "bad_request": GomcRestBadRequestError,
    "forbidden": GomcRestForbiddenError,
    "connection_error": GomcRestConnectionError,
    "busy": GomcRestBusyError,
    "queue_closed": GomcRestQueueClosedError,
    "request_canceled": GomcRestRequestCanceledError,
    "request_timeout": GomcRestRequestTimeoutError,
}

MINIMUM_SUPPORTED_GOMC_REST_VERSION = "v0.10.0"
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_MAX_REDIRECTS = 5


class ResponseLike(Protocol):
    status_code: int
    text: str

    @property
    def ok(self) -> bool: ...

    def json(self) -> Any: ...


class SessionLike(Protocol):
    def get(self, url: str, **kwargs: Any) -> ResponseLike: ...

    def post(self, url: str, **kwargs: Any) -> ResponseLike: ...

    def close(self) -> None: ...


class RandomWordWriteItem(TypedDict):
    """Word (16-bit) write item. ``addr``: device address, ``value``: int."""

    addr: str
    value: int


class RandomDWordWriteItem(TypedDict):
    """Double-word (32-bit) write item. ``addr``: device address, ``value``: int."""

    addr: str
    value: int


class RandomBitWriteItem(TypedDict):
    """Bit write item for bit devices (e.g. M-series). ``value``: bool (True=ON)."""

    addr: str
    value: bool


RandomWordWritePair = tuple[str, int]
RandomDWordWritePair = tuple[str, int]
RandomBitWritePair = tuple[str, bool]


class _UrllibResponse:
    def __init__(self, status_code: int, body: bytes) -> None:
        self.status_code = status_code
        self._body = body
        self.text = body.decode("utf-8", errors="replace")

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> Any:
        return json.loads(self.text)


class _UrllibSession:
    def __init__(self) -> None:
        self._connections: dict[tuple[str, str, int | None, float | None], Any] = {}

    def get(self, url: str, **kwargs: Any) -> ResponseLike:
        return self._send("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> ResponseLike:
        return self._send("POST", url, **kwargs)

    def close(self) -> None:
        for connection in self._connections.values():
            connection.close()
        self._connections.clear()

    def _send(self, method: str, url: str, **kwargs: Any) -> ResponseLike:
        params = kwargs.get("params")
        timeout = kwargs.get("timeout")
        json_body = kwargs.get("json")
        current_url = _build_url(url, params)
        current_method = method
        headers: dict[str, str] = {}
        current_data: bytes | None = None
        if json_body is not None:
            current_data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        for _ in range(_MAX_REDIRECTS + 1):
            parsed_url = parse.urlsplit(current_url)
            connection = self._get_connection(parsed_url, timeout)
            path = _request_target(parsed_url)
            try:
                connection.request(current_method, path, body=current_data, headers=headers)
                response = connection.getresponse()
                body = response.read()
                location = response.getheader("Location")
                if response.status in _REDIRECT_STATUSES and location:
                    if hasattr(response, "close"):
                        response.close()
                    current_url = parse.urljoin(current_url, location)
                    if response.status in {301, 302, 303} and current_method != "GET":
                        current_method = "GET"
                        current_data = None
                        headers = {}
                    continue
                return _UrllibResponse(response.status, body)
            except Exception:
                self._drop_connection(parsed_url, timeout)
                raise
        raise OSError("too many redirects")

    def _get_connection(
        self, parsed_url: parse.SplitResult, timeout: float | None
    ) -> http_client.HTTPConnection:
        key = _connection_key(parsed_url, timeout)
        connection = self._connections.get(key)
        if connection is None:
            scheme, host, port, _ = key
            connection = _create_http_connection(scheme, host, port, timeout)
            self._connections[key] = connection
        return connection

    def _drop_connection(self, parsed_url: parse.SplitResult, timeout: float | None) -> None:
        try:
            key = _connection_key(parsed_url, timeout)
        except OSError:
            return
        connection = self._connections.pop(key, None)
        if connection is not None:
            connection.close()


def _connection_key(
    parsed_url: parse.SplitResult, timeout: float | None
) -> tuple[str, str, int | None, float | None]:
    scheme = parsed_url.scheme or "http"
    host = parsed_url.hostname
    if host is None:
        raise OSError("host is required")
    try:
        port = parsed_url.port
    except ValueError as exc:
        raise OSError(str(exc)) from exc
    return (scheme, host, port, timeout)


def _create_http_connection(
    scheme: str, host: str, port: int | None, timeout: float | None
) -> http_client.HTTPConnection:
    if scheme == "https":
        return http_client.HTTPSConnection(host, port=port, timeout=timeout)
    if scheme == "http":
        return http_client.HTTPConnection(host, port=port, timeout=timeout)
    raise OSError(f"unsupported URL scheme: {scheme}")


def _create_default_session() -> SessionLike:
    return _UrllibSession()


class PLCClient:
    """HTTP client for the gomc-rest server.

    Use as a context manager so the underlying HTTP connection is closed automatically.
    The connection is only closed when the client owns the session (i.e. ``session``
    was not passed in)::

        with PLCClient("http://192.168.0.1:8080") as plc:
            values = plc.read("D100", 3)

    Args:
        base_url: gomc-rest server URL. Defaults to ``"http://localhost:8080"``.
        timeout: Socket timeout in seconds. Defaults to ``10.0``.
        session: Custom session implementing :class:`SessionLike`. A built-in
            urllib session is created and owned (closed on exit) when omitted.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        timeout: float = 10.0,
        session: SessionLike | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._owned_session = session is None
        self.session = _create_default_session() if session is None else session
        self._cached_version: str | None = None

    def __enter__(self) -> PLCClient:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._owned_session:
            self.session.close()

    def health(self) -> dict[str, Any]:
        """Return the server health status."""
        response = self._request("GET", "/health")
        self._ensure_success(response)
        return _require_json_object(response)

    def metrics(self) -> dict[str, Any]:
        """Return runtime metrics from the server."""
        response = self._request("GET", "/metrics")
        self._ensure_success(response)
        return _require_json_object(response)

    def info(self) -> dict[str, Any]:
        """Return build and configuration info from the server."""
        response = self._request("GET", "/info")
        self._ensure_success(response)
        return _require_json_object(response)

    def version(self) -> str:
        """Return the server version string (e.g. ``"v0.10.0"``). Result is cached."""
        if self._cached_version is not None:
            return self._cached_version
        response = self._request("GET", "/version")
        self._ensure_success(response)
        body = _require_json_object(response)
        version = body.get("version")
        if isinstance(version, str) and version:
            if version != "dev":
                try:
                    _parse_semver(version)
                except ValueError as exc:
                    raise GomcRestError(
                        f"invalid server version string: {version}",
                        response.status_code,
                        "bad_response",
                    ) from exc
            self._cached_version = version
            return version
        raise GomcRestError(
            "response version must be a non-empty string",
            response.status_code,
            "bad_response",
        )

    def is_version_compatible(self, minimum_version: str, *, allow_dev: bool = True) -> bool:
        """Return ``True`` if the server version >= *minimum_version*.

        Args:
            minimum_version: Required minimum version string, e.g. ``"v0.10.0"``.
            allow_dev: Treat ``"dev"`` builds as compatible. Defaults to ``True``.
        """
        return _is_version_compatible(self.version(), minimum_version, allow_dev=allow_dev)

    def is_supported_version(self, *, allow_dev: bool = True) -> bool:
        """Return ``True`` if the server meets the library's minimum version requirement.

        The minimum is :data:`MINIMUM_SUPPORTED_GOMC_REST_VERSION` (``"v0.10.0"``).
        """
        return self.is_version_compatible(MINIMUM_SUPPORTED_GOMC_REST_VERSION, allow_dev=allow_dev)

    def read(
        self, addr: str, count: int = 1, *, dword: bool = False, sint: bool = False
    ) -> list[int] | list[bool]:
        """Read *count* consecutive device values starting at *addr*.

        Returns ``list[int]`` for word/dword devices, or ``list[bool]`` for bit
        devices (e.g. M-series: ``True`` = ON, ``False`` = OFF).

        Args:
            addr: Starting device address (e.g. ``"D100"``, ``"M0"``).
            count: Number of consecutive devices to read. Defaults to ``1``.
            dword: Read as 32-bit double-word values.
            sint: Read as signed integers.

        Example::

            words = plc.read("D100", 3)   # [10, 20, 30]
            bits  = plc.read("M0", 4)     # [True, False, True, False]
        """
        response = self._request(
            "GET",
            "/read",
            params={"addr": addr, "count": count, "dword": dword, "sint": sint},
        )
        return self._read_values(response)

    def write(
        self,
        addr: str,
        values: list[int] | list[bool],
        *,
        dword: bool = False,
        sint: bool = False,
    ) -> None:
        """Write consecutive device values starting at *addr*.

        Use ``list[int]`` for word/dword devices, or ``list[bool]`` for bit
        devices (e.g. M-series: ``True`` = ON, ``False`` = OFF).

        Args:
            addr: Starting device address (e.g. ``"D100"``, ``"M0"``).
            values: Values to write.
            dword: Write as 32-bit double-word values.
            sint: Write as signed integers.

        Note:
            Raises :exc:`GomcRestForbiddenError` if the server was started with ``-readonly``.

        Example::

            plc.write("D100", [10, 20, 30])
            plc.write("M0", [True, False, True])
        """
        self._post_ok(
            "/write",
            params={"addr": addr, "dword": dword, "sint": sint},
            json={"values": list(values)},
        )

    def random_read(
        self, words: list[str] | None = None, dwords: list[str] | None = None
    ) -> dict[str, list[int]]:
        """Read values from multiple non-consecutive addresses.

        Returns ``{"words": [...], "dwords": [...]}`` with values in the same
        order as the input lists. Requires gomc-rest >= ``v0.10.0``.

        Args:
            words: Word (16-bit) device addresses, e.g. ``["D100", "D200"]``.
            dwords: Double-word (32-bit) device addresses, e.g. ``["D300"]``.

        Example::

            result = plc.random_read(words=["D100", "D200"], dwords=["D300"])
            # {"words": [10, 20], "dwords": [65536]}
        """
        if not words and not dwords:
            raise ValueError("random_read requires at least one word or dword address")
        response = self._request(
            "POST",
            "/random-read",
            json={"words": list(words or []), "dwords": list(dwords or [])},
        )
        self._ensure_success(response)
        body = _require_json_object(response)
        random_words = body.get("words")
        random_dwords = body.get("dwords")
        if not isinstance(random_words, list) or not all(
            isinstance(value, int) and not isinstance(value, bool) for value in random_words
        ):
            raise GomcRestError(
                "response words must be a list of ints",
                response.status_code,
                "bad_response",
            )
        if not isinstance(random_dwords, list) or not all(
            isinstance(value, int) and not isinstance(value, bool) for value in random_dwords
        ):
            raise GomcRestError(
                "response dwords must be a list of ints",
                response.status_code,
                "bad_response",
            )
        return {"words": random_words, "dwords": random_dwords}

    def random_write(
        self,
        *,
        words: list[RandomWordWriteItem] | None = None,
        dwords: list[RandomDWordWriteItem] | None = None,
        bits: list[RandomBitWriteItem] | None = None,
    ) -> None:
        """Write values to multiple non-consecutive addresses using dict items.

        Requires gomc-rest >= ``v0.10.0``.

        Args:
            words: Word write items, e.g. ``[{"addr": "D100", "value": 10}]``.
            dwords: Double-word write items.
            bits: Bit write items for bit devices (e.g. M-series).
                ``True`` = ON, ``False`` = OFF.

        Note:
            Raises :exc:`GomcRestForbiddenError` if the server was started with ``-readonly``.

        Example::

            plc.random_write(
                words=[{"addr": "D100", "value": 10}],
                bits=[{"addr": "M0", "value": True}],
            )
        """
        if not words and not dwords and not bits:
            raise ValueError("random_write requires at least one word, dword, or bit item")
        self._post_ok(
            "/random-write",
            json={
                "words": list(words or []),
                "dwords": list(dwords or []),
                "bits": list(bits or []),
            },
        )

    def random_write_pairs(
        self,
        *,
        words: list[RandomWordWritePair] | None = None,
        dwords: list[RandomDWordWritePair] | None = None,
        bits: list[RandomBitWritePair] | None = None,
    ) -> None:
        """Write values to multiple non-consecutive addresses using ``(addr, value)`` tuples.

        A concise alternative to :meth:`random_write`. Requires gomc-rest >= ``v0.10.0``.

        Args:
            words: ``(addr, int)`` tuples for word devices, e.g. ``[("D100", 10)]``.
            dwords: ``(addr, int)`` tuples for double-word devices.
            bits: ``(addr, bool)`` tuples for bit devices (e.g. M-series).
                ``True`` = ON, ``False`` = OFF.

        Note:
            Raises :exc:`GomcRestForbiddenError` if the server was started with ``-readonly``.

        Example::

            plc.random_write_pairs(
                words=[("D100", 10), ("D200", 20)],
                bits=[("M0", True), ("M1", False)],
            )
        """
        if not words and not dwords and not bits:
            raise ValueError("random_write_pairs requires at least one word, dword, or bit item")
        self.random_write(
            words=[{"addr": addr, "value": value} for addr, value in words or []],
            dwords=[{"addr": addr, "value": value} for addr, value in dwords or []],
            bits=[{"addr": addr, "value": value} for addr, value in bits or []],
        )

    def remote_run(self, clear: int = 0, force: bool = False) -> None:
        """Start the PLC program (RUN).

        Requires ``-enable-remote`` on the server (not ``-readonly``).

        Args:
            clear: Clear mode before running (``0`` = none, ``1`` = clear, ``2`` = all-clear).
            force: Force-run even if the PLC is in an error state.
        """
        self._post_ok("/remote/run", params={"clear": clear, "force": force})

    def remote_stop(self) -> None:
        """Stop the PLC program (STOP).

        Requires ``-enable-remote`` on the server (not ``-readonly``).
        """
        self._post_ok("/remote/stop")

    def remote_pause(self, force: bool = False) -> None:
        """Pause the PLC program (PAUSE).

        Requires ``-enable-remote`` on the server (not ``-readonly``).

        Args:
            force: Force-pause even when the PLC would normally reject it.
        """
        self._post_ok("/remote/pause", params={"force": force})

    def remote_latch_clear(self) -> None:
        """Clear the PLC latch memory.

        Requires ``-enable-remote`` on the server (not ``-readonly``).
        """
        self._post_ok("/remote/latch-clear")

    def remote_reset(self) -> None:
        """Reset the PLC. Requires ``-enable-remote`` on the server (not ``-readonly``)."""
        self._post_ok("/remote/reset")

    def _post_ok(
        self, path: str, *, params: dict[str, Any] | None = None, json: dict[str, Any] | None = None
    ) -> None:
        response = self._request("POST", path, params=params, json=json)
        self._ensure_success(response)

    def _request(self, method: str, path: str, **kwargs: Any) -> ResponseLike:
        request_method = self.session.get if method == "GET" else self.session.post
        try:
            return request_method(f"{self.base_url}{path}", timeout=self.timeout, **kwargs)
        except TimeoutError as exc:
            raise GomcRestRequestTimeoutError(str(exc), 0, "request_timeout") from exc
        except error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise GomcRestRequestTimeoutError(str(exc), 0, "request_timeout") from exc
            raise GomcRestConnectionError(str(exc), 0, "connection_error") from exc
        except http_client.HTTPException as exc:
            raise GomcRestConnectionError(str(exc), 0, "connection_error") from exc
        except OSError as exc:
            if isinstance(exc, TimeoutError):
                raise GomcRestRequestTimeoutError(str(exc), 0, "request_timeout") from exc
            raise GomcRestConnectionError(str(exc), 0, "connection_error") from exc

    def _read_values(self, response: ResponseLike) -> list[int] | list[bool]:
        self._ensure_success(response)
        body = _require_json_object(response)
        if "values" not in body:
            raise GomcRestError("response values are missing", response.status_code, "bad_response")
        values = body["values"]
        if not isinstance(values, list):
            raise GomcRestError(
                "response values must be a list",
                response.status_code,
                "bad_response",
            )
        if all(isinstance(value, bool) for value in values):
            return values
        if all(isinstance(value, int) and not isinstance(value, bool) for value in values):
            return values
        raise GomcRestError(
            "response values must contain only ints or only bools",
            response.status_code,
            "bad_response",
        )

    def _ensure_success(self, response: ResponseLike) -> None:
        if response.ok:
            return
        raise_for_error(response)


def raise_for_error(response: ResponseLike) -> None:
    body = _response_body(response)
    code = str(body.get("code", ""))
    message = str(body.get("error", response.text))
    status = _status_from_body(body, response.status_code)
    if code == "plc_error":
        raise GomcRestPLCProtocolError(message, status, code, str(body.get("end_code", "")))
    exc_class = _CODE_TO_EXC.get(code, GomcRestError)
    raise exc_class(message, status, code)


def _response_body(response: ResponseLike) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _require_json_object(response: ResponseLike) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise GomcRestError(
            "response body must be a JSON object",
            response.status_code,
            "bad_response",
        ) from exc
    if isinstance(body, dict):
        return body
    raise GomcRestError("response body must be a JSON object", response.status_code, "bad_response")


def _status_from_body(body: dict[str, Any], fallback_status: int) -> int:
    try:
        return int(body.get("status", fallback_status))
    except (TypeError, ValueError):
        return fallback_status


_SEMVER_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def _is_version_compatible(server_version: str, minimum_version: str, *, allow_dev: bool) -> bool:
    if server_version == "dev":
        return allow_dev
    return _parse_semver(server_version) >= _parse_semver(minimum_version)


def _parse_semver(version: str) -> tuple[int, int, int]:
    match = _SEMVER_PATTERN.fullmatch(version)
    if match is None:
        raise ValueError(f"invalid version string: {version}")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def _build_url(url: str, params: dict[str, Any] | None) -> str:
    if not params:
        return url
    normalized = {
        key: ("true" if value else "false") if isinstance(value, bool) else value
        for key, value in params.items()
    }
    encoded_params = parse.urlencode(normalized)
    separator = "&" if parse.urlsplit(url).query else "?"
    return f"{url}{separator}{encoded_params}"


def _request_target(parsed_url: parse.SplitResult) -> str:
    path = parsed_url.path or "/"
    if parsed_url.query:
        return f"{path}?{parsed_url.query}"
    return path
