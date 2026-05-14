from __future__ import annotations

from typing import Any, Protocol

import requests

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
        self.session = session or requests.Session()

    def __enter__(self) -> PLCClient:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._owned_session:
            self.session.close()

    def health(self) -> dict[str, Any]:
        response = self.session.get(f"{self.base_url}/health", timeout=self.timeout)
        return response.json()

    def read(
        self, addr: str, count: int = 1, *, dword: bool = False, sint: bool = False
    ) -> list[int] | list[bool]:
        response = self.session.get(
            f"{self.base_url}/read",
            params={"addr": addr, "count": count, "dword": dword, "sint": sint},
            timeout=self.timeout,
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
        response = self.session.post(
            f"{self.base_url}{path}", params=params, json=json, timeout=self.timeout
        )
        self._ensure_success(response)

    def _read_values(self, response: ResponseLike) -> list[int] | list[bool]:
        self._ensure_success(response)
        values = response.json().get("values", [])
        if not isinstance(values, list):
            raise PLCError("response values must be a list", response.status_code, "bad_response")
        return values

    def _ensure_success(self, response: ResponseLike) -> None:
        if response.ok:
            return
        raise_for_error(response)


def raise_for_error(response: ResponseLike) -> None:
    body = _response_body(response)
    code = str(body.get("code", ""))
    message = str(body.get("error", response.text))
    status = int(body.get("status", response.status_code))
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