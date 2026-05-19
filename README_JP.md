# gomc-rest-client

[English README](https://github.com/Moge800/gomc_rest_client/blob/main/README.md)

gomc-rest の最新 HTTP API 向け Python 3.10+ クライアントライブラリです。

このパッケージは、三菱 PLC 向け gomc-rest の同期 REST エンドポイントを Python 標準ライブラリのみで利用できるようにし、API のエラーレスポンスを型付き Python 例外へ変換します。

## gomc-rest-client について

このパッケージは gomc-rest 専用のクライアントライブラリです。すでに gomc-rest を利用している場合、または三菱 PLC の操作を gomc-rest の HTTP API 経由で扱いたい場合に使うことを想定しています。

このライブラリ自体が PLC と直接通信するわけではありません。サーバー本体、API の仕様、gomc-rest 自体については、上流プロジェクトを参照してください。

- https://github.com/Moge800/gomc-rest

## インストール

```bash
uv add gomc-rest-client
```

pip を使う場合:

```bash
pip install gomc-rest-client
```

PyPI の公開ページ:

- https://pypi.org/project/gomc-rest-client/

オフライン環境では、あらかじめネットワーク内へ配布した wheel からインストールできます。

```bash
pip install dist/gomc_rest_client-*.whl
```

このパッケージは Python 標準ライブラリ以外の実行時依存を持たないため、wheel を使ったオフライン導入がしやすい構成です。

一方で、開発時には PyYAML、pytest、ruff、ty などの開発用依存を使いますが、これらは実行時には不要です。

開発環境のセットアップ:

```bash
uv sync --group dev
```

オフライン環境へ持ち込む配布物を事前に作る場合は次を実行します。

```bash
uv build
```

## 使い方

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
    random_values = plc.random_read(words=["D100", "D200"], dwords=["D300"])
    plc.random_write(
        words=[{"addr": "D100", "value": 10}],
        dwords=[{"addr": "D300", "value": 65536}],
        bits=[{"addr": "M0", "value": True}],
    )

    try:
        plc.remote_run(clear=0, force=False)
    except GomcRestBusyError:
        pass
    except GomcRestPLCProtocolError as exc:
        print(exc.end_code, exc.message)
```

`random_write()` で複数アドレスを書きたい場合は、`words`、`dwords`、`bits` の各リストに `{ "addr": "...", "value": ... }` 形式の辞書を追加していきます。

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

`random_read()` は辞書ではなく、`words=["D100", "D200"]` のようなアドレス文字列のリストを渡します。

`random_read()` の戻り値は、リクエスト順の `words` と `dwords` を持つ辞書です。

```python
result = plc.random_read(words=["D100", "D200"], dwords=["D300"])
# {"words": [100, 200], "dwords": [65536]}
```

`is_supported_version()` と `is_version_compatible()` は、開発中の gomc-rest main ビルドを扱いやすくするため、デフォルトで `dev` ビルドを互換ありとして扱います。

## 対応する gomc-rest バージョン

このクライアントは gomc-rest `v0.10.0` 以降を対象としています。

`v0.10.0` より古いサーバーはサポート対象外です。特に `/version` エンドポイントを持たないサーバーは、このクライアントの対象外です。

このクライアントはサーバーが `/version`、`/info`、`/metrics`、`/random-read`、`/random-write` を提供している前提です。

実行時にサポート可否を確認したい場合は、`plc.is_supported_version()` を呼ぶか、`MINIMUM_SUPPORTED_GOMC_REST_VERSION` と比較してください。

## 対応 API

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
