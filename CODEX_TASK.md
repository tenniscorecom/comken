# Codex タスク: リポジトリ分割

## 概要

`F:\dev\original_libs`（パッケージ名: comken）を以下の4リポジトリに分割する。

コーディング規約は `CONVENTIONS.md` に従うこと。

---

## 分割構成

| 新リポジトリ | 内容 | 優先度 |
|---|---|---|
| `comken-config` | 設定・共通ユーティリティ | 最優先 |
| `comken-office` | Excel操作（win32com + openpyxl）＋Windows操作 | 次 |
| `comken-salesforce` | Salesforce操作 | 中 |
| `comken-selenium` | Seleniumブラウザ自動化 | 後め |

作成先: `F:\dev\` 配下に各リポジトリを新規作成する。

---

## 追加要件: comken-selenium のバージョン整合チェック

### 背景
- 社内環境ではSeleniumインストール済み・外部ダウンロード不可
- ブラウザは **Microsoft Edge**（Windows Updateで自動更新）
- msedgedriver.exe は Edge 本体と同梱され自動更新される
- ただし稀にバージョンがずれてエラーになるため、起動時に明示的なチェックを入れたい

### 要件
- Seleniumドライバー初期化時（またはモジュール読み込み時）に、Edgeブラウザとmseddgedriverのメジャーバージョンを比較する
- バージョンが一致しない場合、ダウンロード方法などの解決策を含む**明示的なエラーメッセージ**を出す
- チェックに失敗してもSelenium本体の動作は妨げない（警告にとどめるか、フラグで制御できるとなお良い）

---

## 注意事項
- 各リポジトリは独立して `pip install -e .` できる形にする
- comken-config は他の3つが依存する共通基盤になる可能性があるため、依存関係の方向に注意
- 既存の `CONVENTIONS.md` を各リポジトリにコピーする
