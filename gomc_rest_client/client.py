from __future__ import annotations

import json
import re
from typing import Any, Protocol
from urllib import error, parse, request

from .exceptions import (
    BadRequestError,
    BusyError,
    ConnectionError,
    ForbiddenError,
    PLCError,
    PLCProtocolError,
    QueueClosedError,
    RequestCanceledError,
    RequestTimeoutError,
)

_CODE_TO_EXC = {
    "bad_request": BadRequestError,
    "forbidden": ForbiddenError,
    "connection_error": ConnectionError,
    "busy": BusyError,
    "queue_closed": QueueClosedError,
    "request_canceled": RequestCanceledError,
    "request_timeout": RequestTimeoutError,
}

MINIMUM_SUPPORTED_GOMC_REST_VERSION = "v0.6.0"


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
    def get(self, url: str, **kwargs: Any) -> ResponseLike:
        return self._send("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> ResponseLike:
        return self._send("POST", url, **kwargs)

    def close(self) -> None:
        return None

    def _send(self, method: str, url: str, **kwargs: Any) -> ResponseLike:
        params = kwargs.get("params")
        timeout = kwargs.get("timeout")
        json_body = kwargs.get("json")
        full_url = _build_url(url, params)
        headers: dict[str, str] = {}
        data: bytes | None = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        http_request = request.Request(full_url, data=data, headers=headers, method=method)
        try:
            with request.urlopen(http_request, timeout=timeout) as response:
                return _UrllibResponse(response.status, response.read())
        except error.HTTPError as exc:
            return _UrllibResponse(exc.code, exc.read())


def _create_default_session() -> SessionLike:
    return _UrllibSession()


class PLCClient:
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
        response = self._request("GET", "/health")
        self._ensure_success(response)
        return _require_json_object(response)

    def metrics(self) -> dict[str, Any]:
        response = self._request("GET", "/metrics")
        self._ensure_success(response)
        return _require_json_object(response)

    def version(self) -> str:
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
                    raise PLCError(
                        f"invalid server version string: {version}",
                        response.status_code,
                        "bad_response",
                    ) from exc
            self._cached_version = version
            return version
        raise PLCError(
            "response version must be a non-empty string",
            response.status_code,
            "bad_response",
        )

    def is_version_compatible(self, minimum_version: str, *, allow_dev: bool = True) -> bool:
        return _is_version_compatible(self.version(), minimum_version, allow_dev=allow_dev)

    def is_supported_version(self, *, allow_dev: bool = True) -> bool:
        return self.is_version_compatible(MINIMUM_SUPPORTED_GOMC_REST_VERSION, allow_dev=allow_dev)

    def read(
        self, addr: str, count: int = 1, *, dword: bool = False, sint: bool = False
    ) -> list[int] | list[bool]:
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
        self._post_ok(
            "/write",
            params={"addr": addr, "dword": dword, "sint": sint},
            json={"values": list(values)},
        )

    def remote_run(self, clear: int = 0, force: bool = False) -> None:
        self._post_ok("/remote/run", params={"clear": clear, "force": force})

    def remote_stop(self) -> None:
        self._post_ok("/remote/stop")

    def remote_pause(self, force: bool = False) -> None:
        self._post_ok("/remote/pause", params={"force": force})

    def remote_latch_clear(self) -> None:
        self._post_ok("/remote/latch-clear")

    def remote_reset(self) -> None:
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
            raise RequestTimeoutError(str(exc), 0, "request_timeout") from exc
        except error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise RequestTimeoutError(str(exc), 0, "request_timeout") from exc
            raise ConnectionError(str(exc), 0, "connection_error") from exc
        except OSError as exc:
            if isinstance(exc, TimeoutError):
                raise RequestTimeoutError(str(exc), 0, "request_timeout") from exc
            raise ConnectionError(str(exc), 0, "connection_error") from exc

    def _read_values(self, response: ResponseLike) -> list[int] | list[bool]:
        self._ensure_success(response)
        body = _require_json_object(response)
        if "values" not in body:
            raise PLCError("response values are missing", response.status_code, "bad_response")
        values = body["values"]
        if not isinstance(values, list):
            raise PLCError("response values must be a list", response.status_code, "bad_response")
        if all(isinstance(value, bool) for value in values):
            return values
        if all(isinstance(value, int) and not isinstance(value, bool) for value in values):
            return values
        raise PLCError(
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
        raise PLCProtocolError(message, status, code, str(body.get("end_code", "")))
    exc_class = _CODE_TO_EXC.get(code, PLCError)
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
        raise PLCError(
            "response body must be a JSON object",
            response.status_code,
            "bad_response",
        ) from exc
    if isinstance(body, dict):
        return body
    raise PLCError("response body must be a JSON object", response.status_code, "bad_response")


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
    encoded_params = parse.urlencode(params)
    separator = "&" if parse.urlsplit(url).query else "?"
    return f"{url}{separator}{encoded_params}"
