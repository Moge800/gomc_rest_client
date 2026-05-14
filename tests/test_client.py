from __future__ import annotations

from dataclasses import dataclass, field
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


class FakeHTTPResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def close(self) -> None:
        return None


class FakeHTTPConnection:
    def __init__(self, responses: list[FakeHTTPResponse]) -> None:
        self._responses = responses
        self.requests: list[dict[str, Any]] = []
        self.closed = False

    def request(
        self, method: str, path: str, body: bytes | None = None, headers: dict[str, str] | None = None
    ) -> None:
        self.requests.append(
            {"method": method, "path": path, "body": body, "headers": headers or {}}
        )

    def getresponse(self) -> FakeHTTPResponse:
        return self._responses.pop(0)

    def close(self) -> None:
        self.closed = True


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
    created_connections: list[FakeHTTPConnection] = []

    def fake_create_http_connection(
        scheme: str, host: str, port: int | None, timeout: float | None
    ) -> FakeHTTPConnection:
        connection = FakeHTTPConnection([FakeHTTPResponse(200, b'{"ok":true}')])
        created_connections.append(connection)
        assert scheme == "http"
        assert host == "localhost"
        assert port == 8080
        assert timeout == 3.5
        return connection

    monkeypatch.setattr(
        "gomc_rest_client.client._create_http_connection", fake_create_http_connection
    )

    response = _UrllibSession().post(
        "http://localhost:8080/write",
        params={"addr": "D100", "dword": True},
        json={"values": [1, 2]},
        timeout=3.5,
    )

    assert len(created_connections) == 1
    assert created_connections[0].requests == [
        {
            "method": "POST",
            "path": "/write?addr=D100&dword=True",
            "body": b'{"values": [1, 2]}',
            "headers": {"Content-Type": "application/json"},
        }
    ]
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_urllib_session_returns_http_error_response(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_create_http_connection(
        scheme: str, host: str, port: int | None, timeout: float | None
    ) -> FakeHTTPConnection:
        return FakeHTTPConnection(
            [FakeHTTPResponse(403, b'{"status":403,"error":"forbidden","code":"forbidden"}')]
        )

    monkeypatch.setattr(
        "gomc_rest_client.client._create_http_connection", fake_create_http_connection
    )

    response = _UrllibSession().get("http://localhost:8080/remote/run", timeout=3.5)

    assert response.status_code == 403
    assert response.ok is False
    assert response.json() == {"status": 403, "error": "forbidden", "code": "forbidden"}


def test_urllib_session_reuses_connection_for_same_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    created_connections: list[FakeHTTPConnection] = []
    connection = FakeHTTPConnection(
        [
            FakeHTTPResponse(200, b'{"plc_status":"ok","connected":true}'),
            FakeHTTPResponse(200, b'{"request_count":1}'),
        ]
    )

    def fake_create_http_connection(
        scheme: str, host: str, port: int | None, timeout: float | None
    ) -> FakeHTTPConnection:
        created_connections.append(connection)
        return connection

    monkeypatch.setattr(
        "gomc_rest_client.client._create_http_connection", fake_create_http_connection
    )
    session = _UrllibSession()

    first_response = session.get("http://localhost:8080/health", timeout=3.5)
    second_response = session.get("http://localhost:8080/metrics", timeout=3.5)

    assert len(created_connections) == 1
    assert connection.requests == [
        {"method": "GET", "path": "/health", "body": None, "headers": {}},
        {"method": "GET", "path": "/metrics", "body": None, "headers": {}},
    ]
    assert first_response.json() == {"plc_status": "ok", "connected": True}
    assert second_response.json() == {"request_count": 1}


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
    class RaisingHTTPConnection(FakeHTTPConnection):
        def request(
            self, method: str, path: str, body: bytes | None = None, headers: dict[str, str] | None = None
        ) -> None:
            raise exception

    def fake_create_http_connection(
        scheme: str, host: str, port: int | None, timeout: float | None
    ) -> FakeHTTPConnection:
        return RaisingHTTPConnection([])

    monkeypatch.setattr(
        "gomc_rest_client.client._create_http_connection", fake_create_http_connection
    )
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
