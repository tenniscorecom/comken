# Excel API

Excel と CSV は、どちらも `Table` を読み書きする入口です。Excel固有のシート操作だけが `Excel` にあります。
**読み取り専用も含めて `with` の中でだけ操作する**——`with` を外れた `Sheet` / `Excel` /
`ExcelTable` を触ると `TableNotOpenError` で止まる（→ [`with` 必須](#with-必須)）。

```python
from comken.core.table import Table
from comken.toolbox.excel import Excel

with Excel("顧客.xlsx") as excel:
    excel.create_data_sheet("顧客").create_table(
        "顧客", Table(["顧客ID", "氏名"], [{"顧客ID": "001", "氏名": "山田"}])
    )

with Excel("顧客.xlsx", read_only=True) as excel:
    rows = excel.data_sheet("顧客").table().read()
```

## シート名を候補から選ぶ

「古い形式と新しい形式でシート名が違う」「テンプレ更新でリネームされた」のように、
業務ファイルでよくある候補違いを `Excel.find_sheet(*candidates)` で吸収する。
候補を順に試し、最初に見つかった **シート名（str）** を返す。全部無いときは
最後の試行で `SheetNotFoundError`（実在シート一覧入り）をそのまま投げる。
**`Sheet` インスタンスが要るときは戻った名前を `excel.sheet(name)` に渡す。**

```python
with Excel("一覧.xlsx", read_only=True) as excel:
    # config の SHEET_NAME = [Sheet1, 一覧] を渡して、使える方を選ぶ
    candidates = config.SOURCE.SHEET_NAME
    sheet_name = excel.find_sheet(*candidates)  # 見つかった str だけ返す
    rows = excel.read_computed_rows_as_dicts(sheet_name)
```

`excel.sheet(name)` を経由しない理由は、 `sheet()` が未存在の新規ブックで
**自動でリネーム**するため。候補違いのときに知らぬ間にブックが変わるのを防ぐ。
データシート（`PY_` プレフィックス付き）を候補に入れても所属判定はそのままなので、
業務ロジック上は **表示用シート名だけを候補にする** こと。

## データシートとテーブル

`create_data_sheet("顧客")` は `PY_顧客` シートを作ります。テーブル名を省略できるのは、そのシートにテーブルが1つだけある場合です。複数ある場合は `table("名前")` と明示します。シート全体を表として扱う機能はありません。

`create_table("名前", table)` に渡す名前は Excel がテーブル名に使えない形式
（先頭が数字・セル参照と紛らわしい形・空白・特殊文字を含む）で `InvalidTableNameError` が
出ます。エラーメッセージはそのまま非エンジニアへ届くため、**事前に `help` シートなどで
命名ルールを書いておく**のが安全です。

## 表示用シート

帳票のように書式や自由セル配置が必要なシートは `create_sheet("集計")` で作る。シート名はそのまま使われ、`PY_` 接頭辞は付きません。戻り値の `Sheet` ではセル・書式・ウィンドウ固定・列幅・行高などの表示用 API が使えます。`table()` のようなデータシート用 API は `DataSheetAccessError` になります。`create_sheet()` は複数回呼んで何枚でも追加でき、既存テストや管理表の動作は変わりません。

## 数式

- **`read_value` / `read_range` は数式セルで計算結果を返す。** `force_com=True` で
  キャッシュを無視して Excel 実機で強制再計算できる。
- **`replace()` / `append()` が数式を潰すときは `TableFormulaOverwriteError` で止まる。**
  数式を値へ上書きしてよいときだけ `allow_formula_overwrite=True` を明示する
- 数式そのものを読みたいときは `Sheet.read_formula(cell)` を使う
  （`read_value` は計算結果を返すため、数式判定には使えない）

## 保存とCOM

正常に `with` を抜けたときだけ自動保存します。例外終了、`read_only=True`、dry-run では保存しません。保存時は同じフォルダの一時ファイルへ書き、再度開けることとVBAが変化していないことを確認してから元ファイルを置き換えます。

`ExcelTable.read()` はExcelテーブルの `ref` 内だけを読み、常に `Table` を返します。保存済みの数式キャッシュがない場合だけ内部でCOMへ切り替えます。キャッシュの有無にかかわらず再計算した値が必要なら `read(force_com=True)` を使います。シート全体を `Table` としてCOMで読む公開APIはありません。

`Excel(path)` はUNCパス（`\\server\share\...`）なら作業中だけ自動的にローカルコピーを使います。`local_copy=True` で強制、`local_copy=False` で無効にできます。ローカルコピーの変更は明示的な `save()` または正常終了時だけ元パスへ保存され、処理後に削除されます。

既存ブックは表示用シートとデータシートを分け、Pythonから扱う表には `PY_` シートと `PY_T_` テーブルのプレフィックスを付けます。既存のセル範囲を自動でテーブル化することはありません。

## `with` 必須

`CSV` / `Excel` は**読み取り専用でも `with` 必須**。`with` を外れたインスタンスを触ると
`TableNotOpenError` で停止する。`Excel` については、`with` を使わないとローカル作業
コピーが消されず残ってしまう実バグがあるため。

## 関連

- [README](../README.md) — ライブラリ全体の概要
- [公開 API](自動生成/API.md) — 型ヒント付き署名・引数・戻り値・例外

