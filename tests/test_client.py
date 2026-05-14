from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from gomc_rest_client import (
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


class FalseySession(FakeSession):
    def __bool__(self) -> bool:
        return False


def test_health_and_read_write_and_remote_requests() -> None:
    session = FakeSession(
        [
            FakeResponse(payload={"plc_status": "ok", "connected": True}),
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
    assert client.read("D100", 3, dword=True, sint=True) == [10, 20, 30]
    client.write("D100", [1, 2], dword=True)
    client.remote_run(clear=2, force=True)
    client.remote_stop()
    client.remote_pause(force=True)
    client.remote_latch_clear()
    client.remote_reset()

    assert session.calls[1]["params"] == {"addr": "D100", "count": 3, "dword": True, "sint": True}
    assert session.calls[2]["json"] == {"values": [1, 2]}
    assert session.calls[3]["params"] == {"clear": 2, "force": True}
    assert session.calls[5]["params"] == {"force": True}


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
    original_session = PLCClient.__init__.__globals__["requests"].Session
    PLCClient.__init__.__globals__["requests"].Session = lambda: session
    try:
        with PLCClient(session=None):
            pass
    finally:
        PLCClient.__init__.__globals__["requests"].Session = original_session

    assert session.closed is True


def test_falsey_custom_session_is_preserved() -> None:
    session = FalseySession([])
    client = PLCClient(session=session)

    assert client.session is session
    assert client._owned_session is False