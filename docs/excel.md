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
    table = excel.read(sheet_name)  # Table が返る
    for row in table.read_rows():
        ...
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
  キャッシュを無視して Excel 実機で強制再計算できる。`Sheet.read_range` は `Table` を返す。
- **`Excel.read(sheet_name, *, header_row=1, force_com=False) -> Table`** が
  シート全体の見出し付き読み取りの公開 API（`read_computed_rows_as_dicts` の後継）。
  未計算の数式だけ内部でCOMに昇格する。`force_com=True` で強制再計算。
- **`replace()` / `append()` が数式を潰すときは `TableFormulaOverwriteError` で止まる。**
  数式を値へ上書きしてよいときだけ `allow_formula_overwrite=True` を明示する
- 数式そのものを読みたいときは `Sheet.read_formula(cell)` を使う
  （`read_value` は計算結果を返すため、数式判定には使えない）

## 列を1本だけ読む（`read_column`）

`Sheet.read_column(col, *, header_row=1, force_com=False) -> Table` は、1列だけを
見出し付きで読む。最終行はシートの使用範囲（`max_row`）から自動で求めるので、
`read_range(f"{col}1:{col}{最終行}")` のように範囲文字列を自分で組み立てなくてよい。

```python
ids = sheet.read_column("G").column("お客様ID")
```

見出しが同じ列がシート内に複数本あるとき（例: 同時レッスンの「お客様ID」が列ごとに
繰り返し出てくる）に使う。シート全体を `read_range` / `Excel.read()` すると同名見出しの
重複で `TableError` になるが、`read_column` は1列だけを `Table` にするので重複しない。

見出しがシートの1行目にない（タイトル行や結合セルの下にある）ときは `header_row` で
指定する。`header_row=2` なら `G2:G{最終行}` を読み、G2 を見出し・G3 以降をデータとして扱う。

## 保存とCOM

正常に `with` を抜けたときだけ自動保存します。例外終了、`read_only=True`、dry-run では保存しません。保存時は同じフォルダの一時ファイルへ書き、再度開けることとVBAが変化していないことを確認してから元ファイルを置き換えます。

`ExcelTable.read()` はExcelテーブルの `ref` 内だけを読み、常に `Table` を返します。保存済みの数式キャッシュがない場合だけ内部でCOMへ切り替えます。キャッシュの有無にかかわらず再計算した値が必要なら `read(force_com=True)` を使います。シート全体を `Table` としてCOMで読む公開APIはありません。

`Excel(path)` はUNCパス（`\\server\share\...`）なら作業中だけ自動的にローカルコピーを使います。`local_copy=True` で強制、`local_copy=False` で無効にできます。ローカルコピーの変更は明示的な `save()` または正常終了時だけ元パスへ保存され、処理後に削除されます。

既存ブックは表示用シートとデータシートを分け、Pythonから扱う表には `PY_` シートと `PY_T_` テーブルのプレフィックスを付けます。既存のセル範囲を自動でテーブル化することはありません。

## エンジン切り替え（`engine` 引数）

約31シート＋ピボット十数個のようなブックを openpyxl で開くとピボットキャッシュ XML
のパースが遅く、同じファイルを Excel COM（pywin32）経由で開くと速い。そのための
切り替えが `Excel(..., engine="com")`。既定の `engine="openpyxl"` は既存と同じ動作。

```python
with Excel("重い.xlsx", engine="com", local_copy=False) as excel:
    for row in excel.read("Sheet1").read_rows():
        ...
```

- `engine="com"` のとき `Excel` は内部で `ExcelCOMHandler` を保持する。`__enter__` /
  `__exit__` で自動的に開き、COM プロセスは `with` 終了時に必ず閉じる。
- `local_copy` の対応:
  - `True` → `ExcelCOMHandler(local_copy_threshold_mb=0)` で常時ローカルコピー
  - `False` → `ExcelCOMHandler(local_copy_threshold_mb=inf)` でコピーしない
  - `None`（未指定）→ `ExcelCOMHandler` 既定（10 MB 超でコピー）だが、**`__enter__` で
    一度だけ `UserWarning` を出す**。UNC パスでの事故を減らすため、`local_copy=True`
    か `False` を明示することが望ましい。
- `engine="com"` で動く公開 API は薄い範囲のみ: `read()`、`list_sheets()`、
  `count_sheets()`、`last_row(sheet_name)`、`exists_sheet(name)`、および
  `excel.com_handler` プロパティ（`run_macro` / `save_as` などの COM 固有 API への
  エスケープハッチ）。
- `engine="com"` で `sheet()` / `data_sheet()` / `create_sheet()` / `create_data_sheet()` /
  `find_sheet()` / `list_data_sheets()` / `save()` / `run_macro()` を呼ぶと
  `InvalidTableOperationError` で止める（`Sheet` 系は openpyxl 前提のため）。
- pywin32 が無い PC では `engine="com"` 自体を import 段階で使えない。openpyxl 経路は
  pywin32 非依存なので、普段は `engine="openpyxl"` のままで良い。

## 既存セル範囲をテーブル化（`convert_range_to_table`）

表示用シート上に既に書き込まれている表を、そのセル値を保ったまま Excel テーブルに
変換する。`Sheet.create_table()` が「新規 `Table` を書き込んで作る」のに対し、
こちらは「既存の値をそのまま `ref` として登録する」操作。

```python
with Excel("帳票.xlsx") as excel:
    excel.convert_range_to_table(
        "集計",
        range="A1:E100",
        table_name="集計",
    )
```

- 安全性判定: 次のいずれかに該当すれば対応する例外で止める。
  - 見出し行のセルが空 → `EmptyHeaderCellError`
  - 範囲内に結合セルがある（A2 が発火した「見出し行より前の行」はタイトルとして許容）
    → `InvalidTableInputError`
  - 範囲がシートの使用範囲外 → `InvalidTableInputError`
  - データ行の途中に全セル空の行がある → `InvalidTableInputError`（行番号入り）
  - 見出し行に重複がある → `DuplicateHeaderCellError`
  - `table_name` が Excel の命名規則違反 → `InvalidTableNameError`
  - 同名のテーブルが既に存在 → `TableAlreadyExistsError`
- `header_row` 未指定時の自動推定は **A2 ルールだけ**: `range` の先頭行に結合セルが
  あれば次行を見出し行とみなす。それ以外の推定（フォントサイズ差・空白判定など）は
  行わない。事故を減らすため `header_row` は明示することを推奨。
- 表示用シート・データシートどちらでも利用可能。`PY_T_` プレフィックスは補わない
  （指定された名前をそのまま使う）。
- `engine="com"` で呼ぶと `NotImplementedError`（openpyxl 経路のみ対応）。

## `with` 必須

`CSV` / `Excel` は**読み取り専用でも `with` 必須**。`with` を外れたインスタンスを触ると
`TableNotOpenError` で停止する。`Excel` については、`with` を使わないとローカル作業
コピーが消されず残ってしまう実バグがあるため。

## 関連

- [README](../README.md) — ライブラリ全体の概要
- [公開 API](自動生成/API.md) — 型ヒント付き署名・引数・戻り値・例外

