# gomc-rest-client

[日本語版 README](README_JP.md)

Python 3.10+ client library for the latest gomc-rest HTTP API.

This package wraps the synchronous REST endpoints exposed by gomc-rest for Mitsubishi PLC read, write, and remote-control operations using only the Python standard library, and converts API error responses into typed Python exceptions.

## Install

```bash
uv add gomc-rest-client
```

For local development:

```bash
uv sync --group dev
```

## Usage

```python
from gomc_rest_client import (
    MINIMUM_SUPPORTED_GOMC_REST_VERSION,
    BusyError,
    PLCClient,
    PLCProtocolError,
)

with PLCClient("http://192.168.0.1:8080") as plc:
    health = plc.health()
    metrics = plc.metrics()
    version = plc.version()
    is_supported = plc.is_supported_version()
    is_compatible = plc.is_version_compatible(MINIMUM_SUPPORTED_GOMC_REST_VERSION)
    values = plc.read("D100", 3)
    bits = plc.read("M0", 4)
    dwords = plc.read("D100", 2, dword=True)
    signed = plc.read("D100", 3, sint=True)

    plc.write("D100", [10, 20, 30])
    plc.write("M0", [True, False])
    plc.write("D100", [-1, -32768, 32767], sint=True)

    try:
        plc.remote_run(clear=0, force=False)
    except BusyError:
        pass
    except PLCProtocolError as exc:
        print(exc.end_code, exc.message)
```

`is_supported_version()` and `is_version_compatible()` treat `dev` builds as compatible by default so local gomc-rest main builds can pass version checks during development.

## Supported gomc-rest versions

This client supports gomc-rest `v0.6.0` and later.

Servers older than `v0.6.0` are not supported. In particular, servers without the `/version` endpoint are out of scope for this client.

This client expects the server to expose both `/version` and `/metrics`.

If you need to verify the support policy at runtime, call `plc.is_supported_version()` or compare against `MINIMUM_SUPPORTED_GOMC_REST_VERSION`.

## API coverage

- GET /version
- GET /metrics
- GET /health
- GET /read
- POST /write
- POST /remote/run
- POST /remote/stop
- POST /remote/pause
- POST /remote/latch-clear
- POST /remote/reset

Remote-control endpoints require the gomc-rest server to start with `-enable-remote`.

## Development

Run checks with uv:

```bash
uv run pytest
uv run ruff check .
uv run ty check
uv build
```

To publish to PyPI after configuring credentials:

```bash
uv publish
```
