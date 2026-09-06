# Data Loader（CLI 実行）

[README（ドキュメントの入口）へ戻る](../README.md)

README の「Data Loader（CLI 実行）」から移した、Salesforce Data Loader を
Python から呼び出すときの詳しい説明です。

## 概要

Salesforce Data Loader は、Salesforce が配布している大量データ一括変更用の
デスクトップアプリ。インストールすると Windows では `dataloader.bat` のような
実行ファイルが配置され、CLI モードで動かすと `config.properties` と
`process-conf.xml` を読み込んで一括挿入・更新・削除を行う。

comken の `comken.toolbox.dataloader.DataLoaderCLI` は、その **CLI 呼び出しを
Python から扱いやすくする薄ラッパー**。`subprocess.run` の呼び出し・タイムアウト
管理・終了コード確認・成功／エラー CSV の `Table` 読み込みまでを担当する。

**comken は Data Loader 自体のインストールや `config.properties` /
`process-conf.xml` の作成は行わない。** それらは利用者の環境で用意する。
comken はその「呼び出し部分」の差し込み口を提供するだけ。

> **重要: 正確な CLI 構文は環境ごとに確認が必要**
>
> Data Loader のバージョンによって、launcher に渡す引数の形や、CLI モード
> の入り方が異なることがある（例: `run <config_dir>`、`extract` /
> `update` などのサブコマンド名、Java モジュール経由の呼び出し）。
> comken はこの構文を決め打ちしない。**実際に動くコマンドを、ターミナル
> で一度確認してから** `args` に渡す。確認せずに動かない引数を渡しても、
> comken は「Data Loader が 0 以外の終了コードを返した」というエラーしか
> 出せず、原因の特定は利用者に委ねられる。

## 使い方

```python
from comken.toolbox.dataloader import DataLoaderCLI

# launcher_path は自分の Data Loader のバージョンに合わせて指定する。
# 下記は一例。
cli = DataLoaderCLI(
    r"C:\Program Files\salesforce.com\Data Loader\dataloader.bat",
    timeout_seconds=3600,  # 大量データを扱うので既定値でも長め
)

result = cli.run(
    # 引数もバージョン依存。「run <config_dir>」「extract ...」等、
    # 自分の環境で一度ターミナルで動かして確かめてから渡す。
    ["run", str(config_dir)],
    success_csv=config_dir / "success.csv",
    error_csv=config_dir / "error.csv",
)

print(f"成功: {len(result.success)} 件 / 失敗: {len(result.errors)} 件")
for row in result.errors.read_rows():
    print("失敗:", row)
```

`success_csv` / `error_csv` を `None` にすれば、その CSV は読み込まずに空の
`Table` が返る。読み込みが要らないときは省略してよい。

```python
result = cli.run(["run", str(config_dir)])  # success / error CSV は読まない
assert result.success == result.errors == type(result.success)([], [])
```

## 設計判断・注意点

### CLI の構文は comken が決め打ちしない

Data Loader の CLI 呼び出し構文は **バージョンによって変わりうる**。
comken 側で一つの形に決め打ちすると、Data Loader をバージョンアップした瞬間に
全利用箇所が壊れる。確実に作れる部分（subprocess 実行・タイムアウト・終了
コード確認・結果 CSV の読み込み）は comken がしっかり作り込み、環境依存で
断定できない部分（実行ファイルのパス・コマンド引数）は **呼び出し側が渡す**
設計にしている。

### `DataLoaderResult.errors` が空でなくても例外にならない

Data Loader は「プロセスとしては正常終了しつつ、対象レコードの一部分だけ
失敗する」という結果を普通に返す（例: バリデーション違反の行が混ざっていた）。
これは「処理が成功した」とも「失敗した」とも一概に言えない。

comken は **プロセスの異常（終了コード非ゼロ）と、レコード単位の失敗を
区別する**。前者は `DataLoaderExecutionError` などの例外で呼び出し側に
伝えるが、後者は `DataLoaderResult.errors` に `Table` として詰めて返すだけで、
例外にはしない。「成功 0 件・失敗 100 件」と「成功 100 件・失敗 0 件」が
同じ呼び出し方で受け取れるので、利用者側の集計ロジックが分岐を増やさずに済む。

### `launcher_path` の存在確認は `run()` で行う

コンストラクタではファイルの存在を確認しない。コンストラクタと `run()`
呼び出しの間に Data Loader がインストールされる／ファイルが復旧する余地を
残すため（既存の `Excel` クラスなど、「コンストラクタでは開かない、
`__enter__` / 操作時に確認する」設計に倣う趣旨）。

### 大量データを扱うので既定のタイムアウトは長め

`timeout_seconds` の既定値は 3600 秒（1 時間）。数万件以上のバッチでは
数十分かかることも珍しくないため。タイムアウトが足りない場合は
`timeout_seconds` を明示的に引き上げるか、処理対象の件数を減らす。

### 結果 CSV が無いときは例外

正常終了したのに `success_csv` / `error_csv` に指定したパスにファイルが
無いと `DataLoaderResultFileMissingError` が出る。`config.properties`
側の出力先設定と、ここで渡したパスが食い違っている可能性が高い。

## 関連

- [README](../README.md) — ライブラリ全体の概要と環境構築
- [公開 API](自動生成/API.md) — 型ヒント付き署名・引数・戻り値・例外
- [エラー対応ガイド](ERRORS.md) — Data Loader の例外と対処
