# gomc-rest-client

[English README](https://github.com/Moge800/gomc_rest_client/blob/main/README.md)

gomc-rest の最新 HTTP API 向け Python 3.10+ クライアントライブラリです。

このパッケージは、三菱 PLC 向け gomc-rest の同期 REST エンドポイントを Python 標準ライブラリのみで利用できるようにし、API のエラーレスポンスを型付き Python 例外へ変換します。

## インストール

```bash
uv add gomc-rest-client
```

ローカル開発用:

```bash
uv sync --group dev
```

## 使い方

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

`is_supported_version()` と `is_version_compatible()` は、開発中の gomc-rest main ビルドを扱いやすくするため、デフォルトで `dev` ビルドを互換ありとして扱います。

## 対応する gomc-rest バージョン

このクライアントは gomc-rest `v0.6.0` 以降を対象としています。

`v0.6.0` より古いサーバーはサポート対象外です。特に `/version` エンドポイントを持たないサーバーは、このクライアントの対象外です。

このクライアントはサーバーが `/version` と `/metrics` の両方を提供している前提です。

実行時にサポート可否を確認したい場合は、`plc.is_supported_version()` を呼ぶか、`MINIMUM_SUPPORTED_GOMC_REST_VERSION` と比較してください。

## 対応 API

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

リモート操作系エンドポイントを使うには、gomc-rest サーバーを `-enable-remote` 付きで起動する必要があります。

## 開発

uv で各種チェックを実行します。

```bash
uv run pytest
uv run ruff check .
uv run ty check
uv build
```

PyPI 公開用の認証設定後は、次で公開できます。

```bash
uv publish
```
