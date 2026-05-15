from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "gomc-rest-v0.7.0-openapi.yaml"

CLIENT_ROUTE_METHODS = {
    "/version": "get",
    "/metrics": "get",
    "/health": "get",
    "/read": "get",
    "/write": "post",
    "/remote/run": "post",
    "/remote/stop": "post",
    "/remote/pause": "post",
    "/remote/latch-clear": "post",
    "/remote/reset": "post",
}

EXPECTED_OPERATION_ERROR_STATUSES = {
    "/read": {"400", "499", "502", "503", "504"},
    "/write": {"400", "403", "413", "499", "502", "503", "504"},
    "/remote/run": {"400", "403", "499", "502", "503", "504"},
    "/remote/stop": {"400", "403", "499", "502", "503", "504"},
    "/remote/pause": {"400", "403", "499", "502", "503", "504"},
    "/remote/latch-clear": {"400", "403", "499", "502", "503", "504"},
    "/remote/reset": {"400", "403", "499", "502", "503", "504"},
}


def _load_openapi_spec() -> dict[str, Any]:
    with FIXTURE_PATH.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def _response_schema(
    spec: dict[str, Any], path: str, method: str, status_code: str
) -> dict[str, Any]:
    return spec["paths"][path][method]["responses"][status_code]["content"]["application/json"][
        "schema"
    ]


def test_openapi_contract_covers_client_routes_and_methods() -> None:
    spec = _load_openapi_spec()
    paths = spec["paths"]

    for path, method in CLIENT_ROUTE_METHODS.items():
        assert path in paths
        assert method in paths[path]


def test_openapi_contract_keeps_required_fields_for_version_and_metrics() -> None:
    spec = _load_openapi_spec()

    version_required = _response_schema(spec, "/version", "get", "200").get("required", [])
    metrics_required = _response_schema(spec, "/metrics", "get", "200").get("required", [])

    assert "version" in version_required
    assert set(metrics_required) >= {
        "request_count",
        "reconnect_count",
        "plc_error_count",
        "avg_latency_ms",
        "queue_length",
    }


def test_openapi_contract_keeps_client_relevant_error_statuses() -> None:
    spec = _load_openapi_spec()

    for path, expected_statuses in EXPECTED_OPERATION_ERROR_STATUSES.items():
        method = CLIENT_ROUTE_METHODS[path]
        responses = spec["paths"][path][method]["responses"]
        assert set(responses) >= expected_statuses