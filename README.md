# gomc-rest-client

[日本語版 README](https://github.com/Moge800/gomc_rest_client/blob/main/README_JP.md)

Python 3.10+ client library for the latest gomc-rest HTTP API.

This package wraps the synchronous REST endpoints exposed by gomc-rest for Mitsubishi PLC read, write, and remote-control operations using only the Python standard library, and converts API error responses into typed Python exceptions.

## About gomc-rest-client

This package is a dedicated client library for gomc-rest. It is intended for users who already use gomc-rest, or who want to expose Mitsubishi PLC operations through the gomc-rest HTTP API.

This library does not communicate with PLCs directly. If you need the server, API surface, or gomc-rest itself, see the upstream project:

- https://github.com/Moge800/gomc-rest

## Install

```bash
uv add gomc-rest-client
```

With pip:

```bash
pip install gomc-rest-client
```

For offline environments, install from a prebuilt wheel distributed inside your network:

```bash
pip install dist/gomc_rest_client-*.whl
```

This package has no runtime dependencies outside the Python standard library, so wheel-based offline installation is straightforward.

For local development:

```bash
uv sync --group dev
```

To build distributable artifacts before taking them into an offline environment:

```bash
uv build
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
