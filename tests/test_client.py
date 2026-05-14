from __future__ import annotations

import io
from dataclasses import dataclass, field
from email.message import Message
from http import client as http_client
from typing import Any
from urllib import error

import pytest

from gomc_rest_client import (
    MINIMUM_SUPPORTED_GOMC_REST_VERSION,
    BadRequestError,
    BusyError,
    ConnectionError,
    ForbiddenError,
    PLCClient,
    PLCError,
    PLCProtocolError,
    QueueClosedError,
    RequestCanceledError,
    RequestTimeoutError,
)
from gomc_rest_client.client import _UrllibSession


@dataclass
class FakeResponse:
    status_code: int = 200
    payload: Any = field(default_factory=dict)
    text: str = ""

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> Any:
        return self.payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self._responses = responses
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": "GET", "url": url, **kwargs})
        return self._responses.pop(0)

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": "POST", "url": url, **kwargs})
        return self._responses.pop(0)

    def close(self) -> None:
        self.closed = True


class RaisingSession(FakeSession):
    def __init__(self, exception: Exception, method: str) -> None:
        super().__init__([])
        self.exception = exception
        self.method = method

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        if self.method == "GET":
            raise self.exception
        return super().get(url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        if self.method == "POST":
            raise self.exception
        return super().post(url, **kwargs)


class FalseySession(FakeSession):
    def __bool__(self) -> bool:
        return False


class FakeUrlopenResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> FakeUrlopenResponse:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


class TrackableBytesIO(io.BytesIO):
    def __init__(self, initial_bytes: bytes) -> None:
        super().__init__(initial_bytes)
        self.was_closed = False

    def close(self) -> None:
        self.was_closed = True
        super().close()


def test_health_and_read_write_and_remote_requests() -> None:
    session = FakeSession(
        [
            FakeResponse(payload={"plc_status": "ok", "connected": True}),
            FakeResponse(
                payload={
                    "request_count": 1,
                    "reconnect_count": 0,
                    "plc_error_count": 0,
                    "avg_latency_ms": 1.5,
                    "queue_length": 0,
                }
            ),
            FakeResponse(payload={"version": "v0.6.0"}),
            FakeResponse(payload={"values": [10, 20, 30]}),
            FakeResponse(payload={"ok": True}),
            FakeResponse(payload={"ok": True}),
            FakeResponse(payload={"ok": True}),
            FakeResponse(payload={"ok": True}),
            FakeResponse(payload={"ok": True}),
            FakeResponse(payload={"ok": True}),
        ]
    )
    client = PLCClient("http://localhost:8080/", timeout=3.5, session=session)

    assert client.health() == {"plc_status": "ok", "connected": True}
    assert client.metrics() == {
        "request_count": 1,
        "reconnect_count": 0,
        "plc_error_count": 0,
        "avg_latency_ms": 1.5,
        "queue_length": 0,
    }
    assert client.version() == "v0.6.0"
    assert client.read("D100", 3, dword=True, sint=True) == [10, 20, 30]
    client.write("D100", [1, 2], dword=True)
    client.remote_run(clear=2, force=True)
    client.remote_stop()
    client.remote_pause(force=True)
    client.remote_latch_clear()
    client.remote_reset()

    assert session.calls[3]["params"] == {"addr": "D100", "count": 3, "dword": True, "sint": True}
    assert session.calls[4]["json"] == {"values": [1, 2]}
    assert session.calls[5]["params"] == {"clear": 2, "force": True}
    assert session.calls[7]["params"] == {"force": True}


@pytest.mark.parametrize(
    ("server_version", "minimum_version", "allow_dev", "expected"),
    [
        ("v0.6.0", "v0.5.0", True, True),
        ("0.5.0", "v0.5.0", True, True),
        ("v0.4.9", "v0.5.0", True, False),
        ("dev", "v0.5.0", True, True),
        ("dev", "v0.5.0", False, False),
    ],
)
def test_is_version_compatible(
    server_version: str, minimum_version: str, allow_dev: bool, expected: bool
) -> None:
    session = FakeSession([FakeResponse(payload={"version": server_version})])
    client = PLCClient(session=session)

    assert client.is_version_compatible(minimum_version, allow_dev=allow_dev) is expected


def test_version_rejects_malformed_success_payload() -> None:
    session = FakeSession([FakeResponse(payload={"version": 123})])
    client = PLCClient(session=session)

    with pytest.raises(PLCError) as exc_info:
        client.version()

    assert exc_info.value.code == "bad_response"
    assert exc_info.value.message == "response version must be a non-empty string"


def test_is_version_compatible_rejects_malformed_server_version_as_bad_response() -> None:
    session = FakeSession([FakeResponse(payload={"version": "v0.6.0-rc1"})])
    client = PLCClient(session=session)

    with pytest.raises(PLCError) as exc_info:
        client.is_version_compatible("v0.6.0")

    assert exc_info.value.code == "bad_response"
    assert exc_info.value.message == "invalid server version string: v0.6.0-rc1"


def test_is_version_compatible_rejects_invalid_minimum_version() -> None:
    session = FakeSession([FakeResponse(payload={"version": "v0.6.0"})])
    client = PLCClient(session=session)

    with pytest.raises(ValueError, match="invalid version string: latest"):
        client.is_version_compatible("latest")


@pytest.mark.parametrize(
    ("server_version", "allow_dev", "expected"),
    [
        ("v0.6.0", True, True),
        ("v0.6.1", True, True),
        ("v0.5.9", True, False),
        ("dev", True, True),
        ("dev", False, False),
    ],
)
def test_is_supported_version(server_version: str, allow_dev: bool, expected: bool) -> None:
    session = FakeSession([FakeResponse(payload={"version": server_version})])
    client = PLCClient(session=session)

    assert MINIMUM_SUPPORTED_GOMC_REST_VERSION == "v0.6.0"
    assert client.is_supported_version(allow_dev=allow_dev) is expected


def test_version_helpers_reuse_cached_version() -> None:
    session = FakeSession([FakeResponse(payload={"version": "v0.6.0"})])
    client = PLCClient(session=session)

    assert client.version() == "v0.6.0"
    assert client.is_supported_version() is True
    assert client.is_version_compatible("v0.6.0") is True
    assert len(session.calls) == 1
    assert session.calls[0]["url"] == "http://localhost:8080/version"


@pytest.mark.parametrize(
    ("code", "status", "exc_type"),
    [
        ("bad_request", 400, BadRequestError),
        ("forbidden", 403, ForbiddenError),
        ("connection_error", 503, ConnectionError),
        ("busy", 503, BusyError),
        ("queue_closed", 503, QueueClosedError),
        ("request_canceled", 499, RequestCanceledError),
        ("request_timeout", 504, RequestTimeoutError),
        ("unknown", 500, PLCError),
    ],
)
def test_error_dispatch(code: str, status: int, exc_type: type[Exception]) -> None:
    session = FakeSession(
        [
            FakeResponse(
                status_code=status,
                payload={"status": status, "error": code, "code": code},
            )
        ]
    )
    client = PLCClient(session=session)

    with pytest.raises(exc_type) as exc_info:
        client.remote_stop()

    assert str(exc_info.value) == code


def test_plc_protocol_error_captures_end_code() -> None:
    session = FakeSession(
        [
            FakeResponse(
                status_code=502,
                payload={
                    "status": 502,
                    "error": "MC error 0x4000",
                    "code": "plc_error",
                    "end_code": "0x4000",
                },
            )
        ]
    )
    client = PLCClient(session=session)

    with pytest.raises(PLCProtocolError) as exc_info:
        client.remote_reset()

    assert exc_info.value.end_code == "0x4000"


def test_health_raises_typed_error_for_non_2xx_response() -> None:
    session = FakeSession(
        [
            FakeResponse(
                status_code=503,
                payload={"status": 503, "error": "connect: refused", "code": "connection_error"},
            )
        ]
    )
    client = PLCClient(session=session)

    with pytest.raises(ConnectionError):
        client.health()


@pytest.mark.parametrize(
    "payload,error_message",
    [
        ([], "response body must be a JSON object"),
        ({}, "response values are missing"),
        ({"values": "not-a-list"}, "response values must be a list"),
        ({"values": ["bad"]}, "response values must contain only ints or only bools"),
        ({"values": [1, True]}, "response values must contain only ints or only bools"),
    ],
)
def test_read_rejects_malformed_success_payload(payload: Any, error_message: str) -> None:
    session = FakeSession([FakeResponse(payload=payload)])
    client = PLCClient(session=session)

    with pytest.raises(PLCError) as exc_info:
        client.read("D100")

    assert exc_info.value.code == "bad_response"
    assert exc_info.value.message == error_message


def test_context_manager_closes_owned_session() -> None:
    session = FakeSession([])
    original_factory = PLCClient.__init__.__globals__["_create_default_session"]
    PLCClient.__init__.__globals__["_create_default_session"] = lambda: session
    try:
        with PLCClient(session=None):
            pass
    finally:
        PLCClient.__init__.__globals__["_create_default_session"] = original_factory

    assert session.closed is True


def test_urllib_session_builds_query_and_json_body(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(http_request: Any, timeout: float | None = None) -> FakeUrlopenResponse:
        captured["url"] = http_request.full_url
        captured["method"] = http_request.get_method()
        captured["body"] = http_request.data
        captured["content_type"] = http_request.get_header("Content-type")
        captured["timeout"] = timeout
        return FakeUrlopenResponse(200, b'{"ok":true}')

    monkeypatch.setattr("gomc_rest_client.client.request.urlopen", fake_urlopen)

    response = _UrllibSession().post(
        "http://localhost:8080/write",
        params={"addr": "D100", "dword": True},
        json={"values": [1, 2]},
        timeout=3.5,
    )

    assert captured["url"] == "http://localhost:8080/write?addr=D100&dword=True"
    assert captured["method"] == "POST"
    assert captured["body"] == b'{"values": [1, 2]}'
    assert captured["content_type"] == "application/json"
    assert captured["timeout"] == 3.5
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_urllib_session_returns_http_error_response(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(http_request: Any, timeout: float | None = None) -> FakeUrlopenResponse:
        headers = Message()
        raise error.HTTPError(
            url=http_request.full_url,
            code=403,
            msg="Forbidden",
            hdrs=headers,
            fp=io.BytesIO(b'{"status":403,"error":"forbidden","code":"forbidden"}'),
        )

    monkeypatch.setattr("gomc_rest_client.client.request.urlopen", fake_urlopen)

    response = _UrllibSession().get("http://localhost:8080/remote/run", timeout=3.5)

    assert response.status_code == 403
    assert response.ok is False
    assert response.json() == {"status": 403, "error": "forbidden", "code": "forbidden"}


def test_urllib_session_closes_http_error_after_read(monkeypatch: pytest.MonkeyPatch) -> None:
    body = TrackableBytesIO(b'{"status":403,"error":"forbidden","code":"forbidden"}')

    def fake_urlopen(http_request: Any, timeout: float | None = None) -> FakeUrlopenResponse:
        headers = Message()
        raise error.HTTPError(
            url=http_request.full_url,
            code=403,
            msg="Forbidden",
            hdrs=headers,
            fp=body,
        )

    monkeypatch.setattr("gomc_rest_client.client.request.urlopen", fake_urlopen)

    response = _UrllibSession().get("http://localhost:8080/remote/run", timeout=3.5)

    assert response.status_code == 403
    assert body.was_closed is True


@pytest.mark.parametrize(
    ("exception", "exc_type", "code"),
    [
        (TimeoutError("timed out"), RequestTimeoutError, "request_timeout"),
        (http_client.BadStatusLine("bad status"), ConnectionError, "connection_error"),
        (error.URLError("connect failed"), ConnectionError, "connection_error"),
    ],
)
def test_default_transport_failures_raise_typed_exceptions(
    monkeypatch: pytest.MonkeyPatch,
    exception: Exception,
    exc_type: type[PLCError],
    code: str,
) -> None:
    def fake_urlopen(http_request: Any, timeout: float | None = None) -> FakeUrlopenResponse:
        raise exception

    monkeypatch.setattr("gomc_rest_client.client.request.urlopen", fake_urlopen)
    client = PLCClient()

    with pytest.raises(exc_type) as exc_info:
        client.health()

    assert exc_info.value.code == code
    assert exc_info.value.status == 0


def test_falsey_custom_session_is_preserved() -> None:
    session = FalseySession([])
    client = PLCClient(session=session)

    assert client.session is session
    assert client._owned_session is False


@pytest.mark.parametrize(
    ("exception", "exc_type", "code"),
    [
        (TimeoutError("timed out"), RequestTimeoutError, "request_timeout"),
        (OSError("connect failed"), ConnectionError, "connection_error"),
    ],
)
def test_get_transport_failures_raise_typed_exceptions(
    exception: Exception, exc_type: type[PLCError], code: str
) -> None:
    client = PLCClient(session=RaisingSession(exception, "GET"))

    with pytest.raises(exc_type) as exc_info:
        client.health()

    assert exc_info.value.code == code
    assert exc_info.value.status == 0


@pytest.mark.parametrize(
    ("exception", "exc_type", "code"),
    [
        (TimeoutError("timed out"), RequestTimeoutError, "request_timeout"),
        (OSError("connect failed"), ConnectionError, "connection_error"),
    ],
)
def test_post_transport_failures_raise_typed_exceptions(
    exception: Exception, exc_type: type[PLCError], code: str
) -> None:
    client = PLCClient(session=RaisingSession(exception, "POST"))

    with pytest.raises(exc_type) as exc_info:
        client.remote_stop()

    assert exc_info.value.code == code
    assert exc_info.value.status == 0


def test_error_dispatch_falls_back_to_response_status_for_invalid_body_status() -> None:
    session = FakeSession(
        [
            FakeResponse(
                status_code=503,
                payload={"status": None, "error": "connect failed", "code": "connection_error"},
            )
        ]
    )
    client = PLCClient(session=session)

    with pytest.raises(ConnectionError) as exc_info:
        client.remote_stop()

    assert exc_info.value.status == 503
