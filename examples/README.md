# examples — 動くサンプル集

comken の使い方を「動くコード」で覚えるためのサンプル。

## 基本の使い方（basics/）

1つの機能だけを確認したいときは、短い基本サンプルから読む。
どれも外部システムや事前データなしで実行でき、入力データもその場で作る。

| ファイル | 内容 | 実行方法 |
|---|---|---|
| csv_read.py | CsvReader の検索・抽出・索引・グループ化 | `python -m examples.basics.csv_read` |
| csv_write.py | CsvWriter の新規作成・1行/複数行追記 | `python -m examples.basics.csv_write` |
| excel_read.py | ExcelReader の辞書・タプル・逐次読み取り | `python -m examples.basics.excel_read` |
| excel_write.py | ExcelWriter / Sheet で帳票作成・書式設定 | `python -m examples.basics.excel_write` |
| column_mapping.py | コードまたは config.ini の列対応表で Excel へ転記 | `python -m examples.basics.column_mapping` |
| state.py | 前回の実行結果を次回へ持ち越す | `python -m examples.basics.state` |
| logger.py | 単体実行向けのログ設定 | `python -m examples.basics.logger` |
| runtime.py | debug / dry-run の範囲と書き込み抑止 | `python -m examples.basics.runtime` |
| files.py | 日付入りファイルの検索・移動・コピー・zip | `python -m examples.basics.files` |
| utils.py | 差分・再試行・待機・文字列正規化・現在時刻 | `python -m examples.basics.utils` |
| constants.py | 文字コード・色・形式・並び順の定数 | `python -m examples.basics.constants` |
| exceptions.py | comken 例外の粒度別の捕捉 | `python -m examples.basics.exceptions` |

成果物は `examples/basics/output/` に出力される。

## 実務シナリオ（既存サンプル）

複数機能を組み合わせた実務の流れを知りたいときはこちらを読む。
リポジトリのルートから `python -m examples.<フォルダ名>.run` で実行する。

### 一覧（学ぶ順のおすすめ）

| # | フォルダ | 内容 | 主に使うモジュール | 実行条件 |
|---|---|---|---|---|
| 1 | csv_to_excel_report | CSV を読んで Excel レポートを作る | CsvReader / ExcelWriter / Sheet / Color | なし（同梱データで動く） |
| 2 | excel_key_transfer | CSV を参照して Excel に転記（XLOOKUP 的転記と SUMIF 的集計転記） | CsvReader.index / group_by / transfer_by_letter / diff_rows | なし（データを自動生成） |
| 3 | csv_diff_report | 昨日と今日の CSV の差分を色付き Excel レポートに | diff_rows / CsvWriter / set_fill | なし（データを自動生成） |
| 4 | sample_login | ブラウザ自動化（Page Object Model の一式） | Browsers / Page / Locator | Edge + msedgedriver |
| 5 | csv_date_move | CSV の日付列とファイル名の日付が一致したファイルを移動 | CsvReader.first / date_in_name / dry_run | config.ini の作成 |
| 6 | daily_batch_template | 日次バッチの流れ（入力を探す → 加工 → Excel 出力） | comken.toolbox.rpa / FileFinder / ExcelWriter | config.ini + 社内ライブラリ |
| 7 | access_export | Access マクロで整形 → CSV 出力 → Excel 帳票 | AccessDatabase / CsvReader / ExcelWriter | Microsoft Access + パス設定 |
| 8 | outlook_inbox | 受信メール → CSV → 結果メールの下書き | Outlook / MailMessage / CsvWriter | Classic Outlook |
| 9 | copy_then_macro | 当日ファイルをコピー → Excel マクロ → 配布 | FileFinder / ExcelWriter.run_macro / copy_file | Microsoft Excel + パス設定 |

### 実行方法

```bash
# 例: CSV → Excel レポート
python -m examples.csv_to_excel_report.run
```

- 1〜3 は外部システム・ネット接続なしでそのまま動く。出力は各フォルダの `output/` に入る
- 4〜10 は各フォルダの Python ファイル冒頭に書いてある事前準備を済ませてから実行する

> **run.py という名前について**: 実プロジェクトのエントリポイントは規約どおり `main.py`（CONVENTIONS.md 参照）。
> examples 内は複数のサンプルが同居し `python -m examples.<フォルダ名>.run` とモジュール実行するため、
> プロジェクトの main.py と区別して run.py にしている。**サンプルをコピーして実プロジェクトにするときは
> main.py にリネームする**（既存プロジェクトを run.py に合わせる必要はない）。

## 新しいツールを作るときは

VS Code のターミナルで **`python -m comken init プロジェクト名`** を実行する
（`comken/__main__.py` から `comken/tools/new_project.py` を呼ぶ）。
`python -m comken init`（init のみ）で名前を対話入力することもできる。
`comken/templates/新規プロジェクト/` の一式（main.py・config.ini.example・実行.bat・認証情報の登録.bat・docs 3種）が
その名前で作られる。エントリポイントには社内 RPA 基盤の呼び出しが入った状態で出てくる。

`daily_batch_template` は、その中身に書く**処理の流れ**の参考にする。
「入力ファイルを探す → 加工する → Excel を出力する」という実務でいちばん多い構成に、
エラー処理・ログ・config.ini の書き方が入っている。

ブラウザ自動化のツールなら `sample_login` の pages/ 構成（Page Object Model）を合わせて使う。
