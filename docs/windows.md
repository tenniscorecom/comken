# Windows 操作

[README（ドキュメントの入口）へ戻る](../README.md)

README の「Windows」から移した、モジュールを使うときの詳しい説明です。

## Windows

通常の Excel 読み書きは `Excel` と `Table` を使う。数式キャッシュが不足すると
`ExcelTable.read()` が自動で COM に昇格する。`ExcelComHandler` の直接利用は、特殊な
COM 操作やパスワード保存が必要な場合に限定する。

### ExcelComHandler

```python
from comken.toolbox.windows.handler import ExcelComHandler

SHEET = "Sheet1"
DATA_ROW = 2
DATA_COL = 3
CHECK_ROW = 5
MACRO_NAME = "Module1.UpdateData"
READ_PW = "読み取りPW"
WRITE_PW = "書き込みPW"

with ExcelComHandler("data.xlsx") as h:
    value = h.read_cell(SHEET, row=DATA_ROW, col=DATA_COL)
    rows = h.read_rows(SHEET)
    rows = h.read_rows_as_dicts(SHEET)
    last_row = h.last_row(SHEET)

    if h.count_non_empty_cells(SHEET, row=CHECK_ROW) == 0:
        print(f"{CHECK_ROW}行目は空行")

    h.run_macro(MACRO_NAME)

    # 上書き保存。close() は保存せずに閉じるため、変更を残すなら必ず呼ぶ
    h.save()

    # 別名保存。保存形式（FileFormat）は元ファイルと同じ形式が自動で使われる
    h.save_as("output.xlsx", read_pw=READ_PW, write_pw=WRITE_PW)
    # パスワードはそれぞれ省略可。読み取りPWだけ・書き込みPWだけの保護もできる
    # h.save_as("output.xlsx", read_pw=READ_PW)  # 読み取り保護のみ

    # 形式を変換して保存する場合だけ file_format を明示する
    # from comken.constants import FileFormat
    # h.save_as("output.csv", file_format=FileFormat.CSV)
```

列マッピングによる CSV / Excel 間の転記には ``comken.core.table.Transfer`` を使う。
Excel COM は、パスワード保存やマクロなど COM が必要な操作に限定する。

### WindowHandler

```python
from comken.toolbox.windows.handler import WindowHandler

WINDOW_TITLE = "メモ帳"

w = WindowHandler(WINDOW_TITLE)
w.activate() # ウィンドウを前面に表示
w.get_title() # タイトルを取得
```

### RegistryHandler

```python
import win32con
from comken.toolbox.windows.handler import RegistryHandler

SETTING_KEY = "SettingName"

with RegistryHandler(win32con.HKEY_CURRENT_USER, r"Software\MyApp") as r:
    value = r.read(SETTING_KEY)
```

### よく使うフォルダ（Paths）

`Path(__file__).parent / ".." / "Downloads"` のような組み立てをしなくてよい。
Desktop / Downloads は **OneDrive の「既知のフォルダーの移動」にも追従する**
（レジストリから実際の場所を取得するため、`C:\Users\xxx\OneDrive\Desktop` に
リダイレクトされている環境でも正しいパスが返る）。

```python
from comken.toolbox.windows import Paths

Paths.downloads()   # → C:\Users\xxx\Downloads
Paths.desktop()     # → C:\Users\xxx\OneDrive\Desktop（リダイレクトされている場合）
Paths.temp_dir()    # → C:\Users\xxx\AppData\Local\Temp
```

### Excel 孤立プロセスの後始末（is_excel_running / kill_excel）

COM 経由の Excel 自動化は、クラッシュ等で EXCEL.EXE が画面に見えないまま裏に残ることがある。
残った Excel はファイルをロックし続け、次回実行時の原因不明エラーのもとになる。

```python
from comken.toolbox.windows import is_excel_running, kill_excel

# 無人実行の PC: 自動処理の開始前に前回の残骸を片付ける
kill_excel()   # ※ ユーザーが開いている Excel も終了する（未保存の変更は失われる）

# 人が使う PC: 警告だけ出す（作業中の Excel を殺さない）
if is_excel_running():
    logger.warning("Excel が起動中です。前回の処理の残骸の可能性があります")
```

---

## 関連

- [README](../README.md) — ライブラリ全体の概要と環境構築
- [公開 API](自動生成/API.md) — 型ヒント付き署名・引数・戻り値・例外
