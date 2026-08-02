# examples — 動くサンプル集

comken の使い方を「動くコード」で覚えるためのサンプル。
どれもリポジトリのルートから `python -m examples.<フォルダ名>.run` で実行する。

## 一覧（学ぶ順のおすすめ）

| # | フォルダ | 内容 | 主に使うモジュール | 実行条件 |
|---|---|---|---|---|
| 1 | csv_to_excel_report | CSV を読んで Excel レポートを作る | CsvReader / ExcelWriter / Sheet / Color | なし（同梱データで動く） |
| 2 | excel_key_transfer | CSV を参照して Excel に転記（XLOOKUP 的転記と SUMIF 的集計転記） | CsvReader.index / group_by / transfer_by_key / diff_rows | なし（データを自動生成） |
| 3 | csv_diff_report | 昨日と今日の CSV の差分を色付き Excel レポートに | diff_rows / CsvWriter / set_fill | なし（データを自動生成） |
| 4 | sample_login | ブラウザ自動化（Page Object Model の一式） | Browsers / Page / Locator | Edge + msedgedriver |
| 5 | csv_date_move | CSV の日付列とファイル名の日付が一致したファイルを移動 | CsvReader.first / date_in_name / dry_run | config.ini の作成 |
| 6 | daily_batch_template | 日次バッチの流れ（入力を探す → 加工 → Excel 出力） | comken.run / FileFinder / ExcelWriter | config.ini + 社内ライブラリ |
| 7 | access_export | Access マクロで整形 → CSV 出力 → Excel 帳票 | AccessDatabase / CsvReader / ExcelWriter | Microsoft Access + パス設定 |
| 8 | outlook_inbox | 受信メール → CSV → 結果メールの下書き | Outlook / MailMessage / CsvWriter | Classic Outlook |

## 実行方法

```bash
# 例: CSV → Excel レポート
python -m examples.csv_to_excel_report.run
```

- 1〜3 は外部システム・ネット接続なしでそのまま動く。出力は各フォルダの `output/` に入る
- 4〜6 は各フォルダの run.py 冒頭に書いてある事前準備を済ませてから実行する

> **run.py という名前について**: 実プロジェクトのエントリポイントは規約どおり `main.py`（CONVENTIONS.md 参照）。
> examples 内は複数のサンプルが同居し `python -m examples.<フォルダ名>.run` とモジュール実行するため、
> プロジェクトの main.py と区別して run.py にしている。**サンプルをコピーして実プロジェクトにするときは
> main.py にリネームする**（既存プロジェクトを run.py に合わせる必要はない）。

## 新しいツールを作るときは

comken のフォルダにある **`新規プロジェクト作成.bat` をダブルクリック**する。
プロジェクト名を入れると、`templates/新規プロジェクト/` の一式（main.py・config.ini.example・
実行.bat・docs 3種）がその名前で作られる。エントリポイントには社内 RPA 基盤の呼び出しが
入った状態で出てくる。

`daily_batch_template` は、その中身に書く**処理の流れ**の参考にする。
「入力ファイルを探す → 加工する → Excel を出力する」という実務でいちばん多い構成に、
エラー処理・ログ・config.ini の書き方が入っている。

ブラウザ自動化のツールなら `sample_login` の pages/ 構成（Page Object Model）を合わせて使う。

