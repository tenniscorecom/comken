# Windows 操作

[README（ドキュメントの入口）へ戻る](../README.md)

README の「Windows」から移した、モジュールを使うときの詳しい説明です。

## Windows

通常の Excel 読み取りは ExcelReader、書き込みは ExcelWriter（openpyxl）を使うこと。
ExcelComHandler は既存数式の計算結果・マクロ・パスワード保存が必要な場合に限定して使う。

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

**キー突合で転記する（XLOOKUP 的転記）:**

キー列の値で lookup を引き、一致した行に列マッピングに従って値を書き込む。
空行・キーが空の行・lookup にないキーの行は自動でスキップされる。
通常は openpyxl 版（`Sheet.transfer_by_letter`）の方が速い（Excel セクション参照）。

```python
lookup = CsvReader("data.csv").index("注文番号")
# → {"A001": {"注文番号": "A001", "顧客名": "株式会社A", ...}, ...}

MAPPING = {"顧客名": "A", "金額": "B"}  # lookup の列名 → Excel の列レター

with ExcelComHandler("data.xlsx") as h:
    matched = h.transfer_by_letter(SHEET, key_col="Q", lookup=lookup, mapping=MAPPING)
    h.save_as("output.xlsx")

print(f"{matched}件転記した")
```

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
