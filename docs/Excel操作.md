# Excel 操作

README の「ネットワーク・NAS ファイルの読み込み」「Excel」から移した、モジュールを使うときの詳しい説明です。

## ネットワーク・NAS ファイルの読み込み

NAS やネットワークドライブ上のファイルは直接開くと遅い・不安定になる場合がある。

### ExcelReader / ExcelWriter（openpyxl）

読み取りだけなら `ExcelReader`（読み取り専用）、書き込み・保存を行うなら
`ExcelWriter` を使う。どちらも `with` 文で確実に閉じる。

`local_copy_threshold_mb` を超えるファイルは自動でローカルにコピーしてから開く。
`with` ブロックを抜けるとテンポラリファイルは自動削除される。

```python
from comken.excel import ExcelReader

NAS_PATH = r"\\nas-server\share\data.xlsx"
SHEET = "Sheet1"

# 10MB 以上は自動でローカルコピー（デフォルト）
with ExcelReader(NAS_PATH) as f:
    rows = f.read_rows_as_dicts(SHEET)

# 閾値を変える（50MB 以上でコピー）
with ExcelReader(NAS_PATH, local_copy_threshold_mb=50) as f:
    rows = f.read_rows_as_dicts(SHEET)

# ローカルコピーを無効化（社内ルールで不可の場合）
with ExcelReader(NAS_PATH, local_copy_threshold_mb=0) as f:
    rows = f.read_rows_as_dicts(SHEET)
```

### ExcelComHandler（win32com）

win32com は `ExcelReader` / `ExcelWriter` の自動コピー機能がないため、`local_copy` を使う。

```python
from comken.utils.files import local_copy
from comken.windows.handler import ExcelComHandler

NAS_PATH = r"\\nas-server\share\data.xlsx"
SHEET = "Sheet1"

with local_copy(NAS_PATH) as local_path:
    with ExcelComHandler(local_path) as h:
        rows = h.read_rows_as_dicts(SHEET)
```

---

## Excel

数式の計算結果や VBA マクロが必要な場合は自動で win32com にフォールバックする。

```python
from comken.excel import ExcelReader, ExcelWriter

SHEET = "Sheet1"
ROW = 2
COL = 1
MACRO_NAME = "Module1.UpdateData"

# 読み取り
with ExcelReader("data.xlsx") as f:
    rows = f.read_rows(SHEET) # タプルのリスト
    rows = f.read_rows_as_dicts(SHEET) # 辞書のリスト（ヘッダーをキーに）

# ヘッダー行がない Excel は __init__ で列名を渡す（1行目からデータとして読まれる）
with ExcelReader("data.xlsx", headers=["注文番号", "金額", "担当者"]) as f:
    rows = f.read_rows_as_dicts(SHEET)

# 数式の計算結果を読む（openpyxl → win32com 自動フォールバック）
with ExcelReader("data.xlsx") as f:
    rows = f.read_computed_rows(SHEET)

# 書き込み・保存
with ExcelWriter("data.xlsx") as f:
    s = f.sheet(SHEET)
    s.write_cell(row=ROW, col=COL, value="値")
    f.save()
    f.save("output.xlsx") # 別名で保存

# 大量データの読み取り（メモリ効率優先）
with ExcelReader("data.xlsx") as f:
    for row in f.iter_rows(SHEET):
        print(row) # 1行ずつ処理。全行をメモリに乗せない

# 複数ファイルを同時処理する場合（目安: 10ファイル以上）は
# concurrent.futures.ThreadPoolExecutor を使うと高速化できる

# シート単位の書き込みは sheet() のラッパーが楽（sheet_name を毎回渡さなくてよい）
with ExcelWriter("report.xlsx") as f:
    s = f.sheet("Sheet1")
    s["A1"] = "売上レポート"              # セル参照で読み書き
    s.write_row(3, ["日付", "金額"])      # 1行を横並びで書く
    s.append_row(["2026-07-12", 1000])    # 最終行の下に追記
    s.auto_width()                        # 列幅を内容に合わせる（全角対応）
    s.freeze_header()                     # 1行目を固定
    f.save()

# 新規ブックの作成 + 辞書リストの一括書き込み（CSV → Excel レポート）
rows = CsvReader("data.csv").rows()
with ExcelWriter.create(r"C:\作業\report.xlsx") as f:
    s = f.sheet("Sheet1")
    s.write_table(rows)                   # ヘッダー行 + データ行をまとめて書く
    s.auto_width()
    s.freeze_header()
    f.save()

# シートの追加・リネーム・削除
with ExcelWriter.create(r"C:\作業\report.xlsx") as f:
    s = f.add_sheet("集計")
    s.write_table(rows)
    f.rename_sheet("Sheet1", "元データ")
    f.delete_sheet("元データ")
    f.save()

# config.ini の列名マッピングで転記（XLOOKUP 的転記。CSV → Excel の更新など）
# config.ini の [受注_MAPPING] は「取引先 = 顧客名」「金額 = 請求額」と書く
from comken import Config
from comken.csv import CsvReader

config = Config()
lookup = CsvReader("data.csv").index("注文番号")
mapping = config.mapping("受注_MAPPING")

with ExcelWriter("data.xlsx") as f:
    matched = f.sheet(SHEET).transfer_by_mapping(
        key_col="受注番号", lookup=lookup, mapping=mapping
    )
    f.save()  # 書き込み後は save() を忘れずに

# ヘッダーがない、または列位置が固定された Excel は列記号版を使う
# この対応表だけは「転記先の列記号 → 転記元の列名」の向き
column_mapping = {"B": "顧客名", "C": "金額"}
with ExcelWriter("data.xlsx") as f:
    matched = f.sheet(SHEET).transfer_by_key(
        key_col="A", lookup=lookup, column_mapping=column_mapping
    )
    f.save()

# 背景色の設定（よく使う色は Color 定数で指定できる）
from comken.constants import Color

with ExcelWriter("data.xlsx") as f:
    s = f.sheet(SHEET)
    s.set_fill(row=ROW, col=COL, color=Color.YELLOW)
    s.set_fill(row=ROW, col=COL, color=Color.RED)
    s.set_fill(row=ROW, col=COL, color="CCE5FF") # 定数にない色は16進で
    f.save()

# 構造化テーブル
with ExcelWriter.create("table.xlsx") as f:
    s = f.sheet("Sheet1")
    s.write_table(rows)
    s.add_table("売上", f"A1:C{len(rows) + 1}")
    f.save()

# 既存テーブルのデータを洗い替える（範囲も自動で調整される）
with ExcelWriter("table.xlsx") as f:
    s = f.sheet("Sheet1")
    s.replace_table("売上", rows)
    s.append_to_table("売上", [{"商品": "D", "金額": 400}])
    f.save()

# 数式は文字列で書く。構造化参照も同じ
TABLE_NAME = "月次売上"
AMOUNT_HEADER = "金額"
with ExcelWriter("data.xlsx") as f:
    s = f.sheet(SHEET)
    s["A4"] = "=SUM(A1:A3)"
    s["D1"] = f"=SUM({TABLE_NAME}[{AMOUNT_HEADER}])"
    f.save()

# 用意している色: RED / PINK / ORANGE / YELLOW / LIGHT_YELLOW / GREEN / LIGHT_GREEN
#                BLUE / LIGHT_BLUE / PURPLE / GRAY / LIGHT_GRAY / WHITE / BLACK

# VBA マクロの実行（常に win32com を使用）
from comken.windows import ExcelComHandler

with ExcelComHandler("data.xlsm") as f:
    f.run_macro(MACRO_NAME)
```

テーブルの作成・名前変更・削除は人が Excel で行い、プログラムでは既存テーブルの中の
データを追記・全消去・洗い替えする。`add_table()` は新規レポートを作る場合に限って使う。

### 数式の扱い

`s["A4"] = "=SUM(A1:A3)"` のように数式を文字列として書けば、ファイルには保存される。
ただし openpyxl は数式を計算も検証もしない。計算結果を Python 側で読む必要がある場合は、
既存の数式セルを必要に応じて COM で再計算する `read_computed_rows()` を使う。

**comken を使うプログラムから数式を入れることは避ける。** 書いた数式の正しさを保証するための
再計算・検査は、値の転記に対してコストが重いためである。計算は Power Query や、
プログラムが触らない範囲（人が用意した数式列・集計シート）で行い、プログラムは値の
書き込みと転記に徹する。

**数万行クラスの大きいファイルを扱うときのベストプラクティス:**

| やりたいこと | 方法 |
|---|---|
| 大量行を読む | `iter_rows()` で1行ずつ処理する（全行をメモリに乗せない） |
| NAS 上の大きいファイル | `local_copy_threshold_mb` の自動ローカルコピーに任せる（デフォルト10MB） |
| 大量行への書き込み | 1セルずつ書かず、行は `Sheet.write_rows()`、見出し＋データは `Sheet.write_table()` でまとめて書く |
| キー突合転記が大量行 | ヘッダーがある帳票は `transfer_by_mapping()`、列位置が固定なら `transfer_by_key()` を使う。通常は高速な openpyxl 版を優先する |

---

## 関連

- [README](../README.md) — ライブラリ全体の概要と環境構築
- [公開 API](API.md) — 型ヒント付き署名・引数・戻り値・例外
