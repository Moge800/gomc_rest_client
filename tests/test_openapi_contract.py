from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "gomc-rest-v1.3.0-openapi.yaml"
PINNED_OPENAPI_VERSION = "v1.3.0"

CLIENT_ROUTE_METHODS = {
    "/version": "get",
    "/info": "get",
    "/metrics": "get",
    "/health": "get",
    "/read": "get",
    "/write": "post",
    "/random-read": "post",
    "/random-write": "post",
    "/remote/run": "post",
    "/remote/stop": "post",
    "/remote/pause": "post",
    "/remote/latch-clear": "post",
    "/remote/reset": "post",
}

EXPECTED_OPERATION_ERROR_STATUSES = {
    "/read": {"400", "499", "502", "503", "504"},
    "/write": {"400", "403", "413", "499", "502", "503", "504"},
    "/random-read": {"400", "413", "499", "502", "503", "504"},
    "/random-write": {"400", "403", "413", "499", "502", "503", "504"},
    "/remote/run": {"400", "403", "499", "502", "503", "504"},
    "/remote/stop": {"400", "403", "499", "502", "503", "504"},
    "/remote/pause": {"400", "403", "499", "502", "503", "504"},
    "/remote/latch-clear": {"400", "403", "499", "502", "503", "504"},
    "/remote/reset": {"400", "403", "499", "502", "503", "504"},
}

EXPECTED_QUERY_PARAMETERS = {
    "/read": {
        "addr": {"required": True, "type": "string"},
        "count": {"required": False, "type": "integer"},
        "dword": {"required": False, "type": "boolean"},
        "sint": {"required": False, "type": "boolean"},
    },
    "/write": {
        "addr": {"required": True, "type": "string"},
        "dword": {"required": False, "type": "boolean"},
        "sint": {"required": False, "type": "boolean"},
    },
    "/remote/run": {
        "clear": {"required": False, "type": "integer"},
        "force": {"required": False, "type": "boolean"},
    },
    "/remote/pause": {
        "force": {"required": False, "type": "boolean"},
    },
}

EXPECTED_INFO_RESPONSE_FIELDS = {
    "version": {"type": "string"},
    "gomcprotocol_version": {"type": "string"},
    "host": {"type": "string"},
    "port": {"type": "integer"},
    "frame": {"type": "string"},
    "transport": {"type": "string"},
    "mode": {"type": "string"},
    "listen_addrs": {"type": "array"},
    "readonly": {"type": "boolean"},
    "enable_remote": {"type": "boolean"},
}

EXPECTED_VERSION_RESPONSE_FIELDS = {
    "version": {"type": "string"},
}

EXPECTED_METRICS_RESPONSE_FIELDS = {
    "request_count": {"type": "integer"},
    "reconnect_count": {"type": "integer"},
    "timeout_count": {"type": "integer"},
    "plc_error_count": {"type": "integer"},
    "avg_latency_ms": {"type": "number"},
    "recent_avg_latency_ms": {"type": "number"},
    "queue_length": {"type": "integer"},
    "client_request_count": {"type": "integer"},
    "busy_count": {"type": "integer"},
    "client_avg_latency_ms": {"type": "number"},
    "client_recent_avg_latency_ms": {"type": "number"},
}

EXPECTED_ERROR_CODES = {
    "/read": {
        "400": {"bad_request"},
        "499": {"request_canceled"},
        "502": {"plc_error"},
        "503": {"busy", "connection_error", "queue_closed"},
        "504": {"request_timeout"},
    },
    "/write": {
        "400": {"bad_request"},
        "403": {"forbidden"},
        "413": {"bad_request"},
        "499": {"request_canceled"},
        "502": {"plc_error"},
        "503": {"busy", "connection_error", "queue_closed"},
        "504": {"request_timeout"},
    },
    "/random-read": {
        "400": {"bad_request"},
        "413": {"bad_request"},
        "499": {"request_canceled"},
        "502": {"plc_error"},
        "503": {"busy", "connection_error", "queue_closed"},
        "504": {"request_timeout"},
    },
    "/random-write": {
        "400": {"bad_request"},
        "403": {"forbidden"},
        "413": {"bad_request"},
        "499": {"request_canceled"},
        "502": {"plc_error"},
        "503": {"busy", "connection_error", "queue_closed"},
        "504": {"request_timeout"},
    },
    "/remote/run": {
        "400": {"bad_request"},
        "403": {"forbidden"},
        "499": {"request_canceled"},
        "502": {"plc_error"},
        "503": {"busy", "connection_error", "queue_closed"},
        "504": {"request_timeout"},
    },
    "/remote/stop": {
        "400": {"bad_request"},
        "403": {"forbidden"},
        "499": {"request_canceled"},
        "502": {"plc_error"},
        "503": {"busy", "connection_error", "queue_closed"},
        "504": {"request_timeout"},
    },
    "/remote/pause": {
        "400": {"bad_request"},
        "403": {"forbidden"},
        "499": {"request_canceled"},
        "502": {"plc_error"},
        "503": {"busy", "connection_error", "queue_closed"},
        "504": {"request_timeout"},
    },
    "/remote/latch-clear": {
        "400": {"bad_request"},
        "403": {"forbidden"},
        "499": {"request_canceled"},
        "502": {"plc_error"},
        "503": {"busy", "connection_error", "queue_closed"},
        "504": {"request_timeout"},
    },
    "/remote/reset": {
        "400": {"bad_request"},
        "403": {"forbidden"},
        "499": {"request_canceled"},
        "502": {"plc_error"},
        "503": {"busy", "connection_error", "queue_closed"},
        "504": {"request_timeout"},
    },
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


def _operation(spec: dict[str, Any], path: str, method: str) -> dict[str, Any]:
    return spec["paths"][path][method]


def _parameter_by_name(operation: dict[str, Any], name: str) -> dict[str, Any]:
    return next(parameter for parameter in operation["parameters"] if parameter["name"] == name)


def _resolve_response(
    spec: dict[str, Any], response: dict[str, Any]
) -> dict[str, Any]:
    ref = response.get("$ref")
    if ref is None:
        return response
    _, _, component_path = ref.partition("#/")
    resolved: Any = spec
    for key in component_path.split("/"):
        resolved = resolved[key]
    if not isinstance(resolved, dict):
        raise TypeError(f"response reference did not resolve to an object: {ref}")
    return resolved


def _resolve_schema(spec: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if ref is None:
        return schema
    _, _, component_path = ref.partition("#/")
    resolved: Any = spec
    for key in component_path.split("/"):
        resolved = resolved[key]
    if not isinstance(resolved, dict):
        raise TypeError(f"schema reference did not resolve to an object: {ref}")
    return resolved


def _response_codes(spec: dict[str, Any], path: str, method: str, status_code: str) -> set[str]:
    response = _resolve_response(spec, _operation(spec, path, method)["responses"][status_code])
    json_content = response.get("content", {}).get("application/json")
    if json_content is None:
        return set()
    examples = json_content.get("examples")
    if examples:
        return {
            example["value"]["code"]
            for example in examples.values()
            if "value" in example and "code" in example["value"]
        }
    example = json_content.get("example")
    if isinstance(example, dict) and "code" in example:
        return {example["code"]}
    schema = _resolve_schema(spec, json_content.get("schema", {}))
    code_schema = schema.get("properties", {}).get("code", {})
    enum_values = code_schema.get("enum")
    if enum_values:
        return set(enum_values)
    return set()


def test_openapi_contract_covers_client_routes_and_methods() -> None:
    spec = _load_openapi_spec()
    paths = spec["paths"]

    for path, method in CLIENT_ROUTE_METHODS.items():
        assert path in paths
        assert method in paths[path]


def test_openapi_contract_uses_pinned_release_version() -> None:
    spec = _load_openapi_spec()

    assert spec["info"]["version"] == PINNED_OPENAPI_VERSION


def test_openapi_contract_keeps_required_fields_for_info_version_and_metrics() -> None:
    spec = _load_openapi_spec()

    info_schema = _response_schema(spec, "/info", "get", "200")
    version_schema = _response_schema(spec, "/version", "get", "200")
    metrics_schema = _response_schema(spec, "/metrics", "get", "200")
    info_required = info_schema.get("required", [])
    version_required = version_schema.get("required", [])
    metrics_required = metrics_schema.get("required", [])

    assert set(info_required) >= set(EXPECTED_INFO_RESPONSE_FIELDS)
    assert "version" in version_required
    assert set(metrics_required) >= {
        "request_count",
        "reconnect_count",
        "timeout_count",
        "plc_error_count",
        "avg_latency_ms",
        "recent_avg_latency_ms",
        "queue_length",
        "client_request_count",
        "busy_count",
        "client_avg_latency_ms",
        "client_recent_avg_latency_ms",
    }

    for name, expected in EXPECTED_INFO_RESPONSE_FIELDS.items():
        assert info_schema["properties"][name]["type"] == expected["type"]

    for name, expected in EXPECTED_VERSION_RESPONSE_FIELDS.items():
        assert version_schema["properties"][name]["type"] == expected["type"]

    for name, expected in EXPECTED_METRICS_RESPONSE_FIELDS.items():
        assert metrics_schema["properties"][name]["type"] == expected["type"]


def test_openapi_contract_keeps_client_required_read_and_write_fields() -> None:
    spec = _load_openapi_spec()

    write_operation = _operation(spec, "/write", "post")
    random_read_operation = _operation(spec, "/random-read", "post")
    random_write_operation = _operation(spec, "/random-write", "post")
    read_response_required = _response_schema(spec, "/read", "get", "200").get("required", [])
    write_body_schema = write_operation["requestBody"]["content"]["application/json"]["schema"]
    random_read_body_schema = random_read_operation["requestBody"]["content"][
        "application/json"
    ]["schema"]
    random_write_body_schema = random_write_operation["requestBody"]["content"][
        "application/json"
    ]["schema"]
    random_read_response_required = _response_schema(spec, "/random-read", "post", "200").get(
        "required", []
    )

    assert "values" in read_response_required
    assert write_operation["requestBody"]["required"] is True
    assert "values" in write_body_schema.get("required", [])
    assert random_read_operation["requestBody"]["required"] is True
    assert random_write_operation["requestBody"]["required"] is True
    assert set(random_read_response_required) >= {"words", "dwords", "bits"}
    assert set(random_read_body_schema.get("properties", {})) >= {"words", "dwords", "bits"}
    assert set(random_write_body_schema.get("properties", {})) >= {"words", "dwords", "bits"}

    for path, expected_parameters in EXPECTED_QUERY_PARAMETERS.items():
        operation = _operation(spec, path, CLIENT_ROUTE_METHODS[path])
        for name, expected in expected_parameters.items():
            parameter = _parameter_by_name(operation, name)
            assert parameter["required"] is expected["required"]
            assert parameter["schema"]["type"] == expected["type"]


def test_openapi_contract_keeps_client_relevant_error_statuses() -> None:
    spec = _load_openapi_spec()

    for path, expected_statuses in EXPECTED_OPERATION_ERROR_STATUSES.items():
        method = CLIENT_ROUTE_METHODS[path]
        responses = spec["paths"][path][method]["responses"]
        assert set(responses) >= expected_statuses


def test_openapi_contract_keeps_client_relevant_error_codes() -> None:
    spec = _load_openapi_spec()

    for path, status_to_codes in EXPECTED_ERROR_CODES.items():
        method = CLIENT_ROUTE_METHODS[path]
        for status_code, expected_codes in status_to_codes.items():
            assert _response_codes(spec, path, method, status_code) >= expected_codes
