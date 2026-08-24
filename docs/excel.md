# Excel API

Excel と CSV は、どちらも `Table` を読み書きする入口です。Excel固有のシート操作だけが `Excel` にあります。

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

## データシートとテーブル

`create_data_sheet("顧客")` は `PY_顧客` シートを作ります。テーブル名を省略できるのは、そのシートにテーブルが1つだけある場合です。複数ある場合は `table("名前")` と明示します。シート全体を表として扱う機能はありません。

## 表示用シート

帳票のように書式や自由セル配置が必要なシートは `create_sheet("集計")` で作る。シート名はそのまま使われ、`PY_` 接頭辞は付きません。戻り値の `Sheet` ではセル・書式・ウィンドウ固定・列幅・行高などの表示用 API が使えます。`table()` のようなデータシート用 API は `DataSheetAccessError` になります。`create_sheet()` は複数回呼んで何枚でも追加でき、既存テストや管理表の動作は変わりません。

## 保存とCOM

正常に `with` を抜けたときだけ自動保存します。例外終了、`read_only=True`、dry-run では保存しません。保存時は同じフォルダの一時ファイルへ書き、再度開けることとVBAが変化していないことを確認してから元ファイルを置き換えます。

`ExcelTable.read()` はExcelテーブルの `ref` 内だけを読み、常に `Table` を返します。保存済みの数式キャッシュがない場合だけ内部でCOMへ切り替えます。キャッシュの有無にかかわらず再計算した値が必要なら `read(force_com=True)` を使います。シート全体を `Table` としてCOMで読む公開APIはありません。

`Excel(path)` はUNCパス（`\\server\share\...`）なら作業中だけ自動的にローカルコピーを使います。`local_copy=True` で強制、`local_copy=False` で無効にできます。ローカルコピーの変更は明示的な `save()` または正常終了時だけ元パスへ保存され、処理後に削除されます。

既存ブックは表示用シートとデータシートを分け、Pythonから扱う表には `PY_` シートと `PY_T_` テーブルのプレフィックスを付けます。既存のセル範囲を自動でテーブル化することはありません。
