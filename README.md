# gomc-rest-client

Python 3.10+ client library for the latest gomc-rest HTTP API.

This package wraps the synchronous REST endpoints exposed by gomc-rest for Mitsubishi PLC read, write, and remote-control operations. It uses requests internally and converts API error responses into typed Python exceptions.

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
from gomc_rest_client import BusyError, PLCClient, PLCProtocolError

with PLCClient("http://192.168.0.1:8080") as plc:
    health = plc.health()
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

## API coverage

- GET /health
- GET /read
- POST /write
- POST /remote/run
- POST /remote/stop
- POST /remote/pause
- POST /remote/latch-clear
- POST /remote/reset

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