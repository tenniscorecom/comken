# Data Loader（CLI 実行）

[README（ドキュメントの入口）へ戻る](../README.md)

README の「Data Loader（CLI 実行）」から移した、Salesforce Data Loader を
Python から呼び出すときの詳しい説明です。

## 概要

Salesforce Data Loader は、Salesforce が配布している大量データ一括変更用の
デスクトップアプリ。インストールすると Windows では `dataloader.bat` のような
実行ファイルが配置され、CLI モードで動かすと `config.properties` と
`process-conf.xml` を読み込んで一括挿入・更新・削除を行う。

comken の `comken.toolbox.salesforce.dataloader.DataLoaderCLI` は、その **CLI 呼び出しを
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
from comken.toolbox.salesforce.dataloader import DataLoaderCLI

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
for row in result.errors.to_rows():
    print("失敗:", row)
```

`success_csv` / `error_csv` を `None` にすれば、その CSV は読み込まずに空の
`Table` が返る。読み込みが要らないときは省略してよい。

```python
result = cli.run(["run", str(config_dir)])  # success / error CSV は読まない
assert result.success == result.errors == type(result.success)([], [])
```

## 設計判断・注意点

**CLI 構文を comken が決め打ちしない理由・`launcher_path` の存在確認を
`run()` まで遅らせる理由・既定タイムアウトが長い理由・
`DataLoaderResult.errors` が空でなくても例外にならない理由は、ここでは
重複させずコードの docstring（`DataLoaderCLI` / `DataLoaderCLI.run()` /
`DataLoaderResult`）を正とする** — `docs/` は共有サーバーへ配布されず
docstring だけが実際に利用プロジェクト側へ届くため、二重管理を避けて
そちらに寄せている。[自動生成 API.md](自動生成/API.md) にも同じ docstring が載る。

### 結果 CSV が無いときの対処

`DataLoaderResultFileMissingError` が出たら、`config.properties` 側の
出力先設定と、`run()` に渡した `success_csv` / `error_csv` のパスが
食い違っている可能性が高い。

## 関連

- [README](../README.md) — ライブラリ全体の概要と環境構築
- [公開 API](自動生成/API.md) — 型ヒント付き署名・引数・戻り値・例外
- [エラー対応ガイド](ERRORS.md) — Data Loader の例外と対処
