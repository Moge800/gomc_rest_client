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

PyPI project page:

- https://pypi.org/project/gomc-rest-client/

For offline environments, install from a prebuilt wheel distributed inside your network:

```bash
pip install dist/gomc_rest_client-*.whl
```

This package has no runtime dependencies outside the Python standard library, so wheel-based offline installation is straightforward.

Development tasks currently use dev dependencies such as PyYAML, pytest, ruff, and ty, but they are not required at runtime.

To set up the development environment:

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
    GomcRestBusyError,
    GomcRestPLCProtocolError,
    PLCClient,
)

with PLCClient("http://192.168.0.1:8080") as plc:
    health = plc.health()
    metrics = plc.metrics()
    info = plc.info()
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
    random_values = plc.random_read(words=["D100", "D200"], dwords=["D300"], bits=["D100.1", "M0"])
    plc.random_write_pairs(
        words=[("D100", 10)],
        dwords=[("D300", 65536)],
        bits=[("M0", True)],
    )

    try:
        plc.remote_run(clear=0, force=False)
    except GomcRestBusyError:
        pass
    except GomcRestPLCProtocolError as exc:
        print(exc.end_code, exc.message)
```

If you want to write multiple non-contiguous addresses, `random_write_pairs()` accepts `(addr, value)` pairs directly.

```python
plc.random_write_pairs(
    words=[("D100", 10), ("D200", 20)],
    dwords=[("D300", 65536), ("D302", 123456)],
    bits=[("M0", True), ("M10", False)],
)
```

If you prefer the server payload shape directly, `random_write()` still accepts `{ "addr": "...", "value": ... }` dictionaries.

```python
plc.random_write(
    words=[
        {"addr": "D100", "value": 10},
        {"addr": "D200", "value": 20},
    ],
    dwords=[
        {"addr": "D300", "value": 65536},
        {"addr": "D302", "value": 123456},
    ],
    bits=[
        {"addr": "M0", "value": True},
        {"addr": "M10", "value": False},
    ],
)
```

`random_read()` takes address-string lists. `bits` accepts up to 255 addresses total: word-device bit access (e.g. `D100.1`) and bit devices (e.g. `M0`). Bit devices are capped at 16 per request by the server; word-device bit access has no such limit.

The return value is a dictionary with `words`, `dwords`, and `bits` lists in request order.

```python
result = plc.random_read(words=["D100", "D200"], dwords=["D300"], bits=["D100.1", "M0"])
# {"words": [100, 200], "dwords": [65536], "bits": [True, False]}
```

`is_supported_version()` and `is_version_compatible()` treat `dev` builds as compatible by default so local gomc-rest main builds can pass version checks during development.

## Supported gomc-rest versions

This client supports gomc-rest `v1.3.0` and later.

Servers older than `v1.3.0` are not supported because this client relies on the `v1.3.0` `bits` support in `/random-read` and the `timeout_count` field added to `/metrics` in that release.

This client expects the server to expose `/version`, `/info`, `/metrics`, `/random-read`, and `/random-write`.

If you need to verify the support policy at runtime, call `plc.is_supported_version()` or compare against `MINIMUM_SUPPORTED_GOMC_REST_VERSION`.

## API coverage

- GET /version
- GET /info
- GET /metrics
- GET /health
- GET /read
- POST /write
- POST /random-read
- POST /random-write
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
