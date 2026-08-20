# Excel 操作

[README（ドキュメントの入口）へ戻る](../README.md)

README の「ネットワーク・NAS ファイルの読み込み」「Excel」から移した、モジュールを使うときの詳しい説明です。

## ネットワーク・NAS ファイルの読み込み

NAS やネットワークドライブ上のファイルは直接開くと遅い・不安定になる場合がある。

### ExcelReader / ExcelWriter（openpyxl）

読み取りだけなら `ExcelReader`（読み取り専用）、書き込み・保存を行うなら
`ExcelWriter` を使う。どちらも `with` 文で確実に閉じる。

`local_copy_threshold_mb` を超えるファイルは自動でローカルにコピーしてから開く。
`with` ブロックを抜けるとテンポラリファイルは自動削除される。

```python
from comken.toolbox.excel import ExcelReader

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

`ExcelReader` / `ExcelWriter` と同じく、`local_copy_threshold_mb` を超えるサイズの
ファイルは自動でローカルコピーしてから開く（NAS・共有サーバー上のファイル向け）。
`0` を指定すれば無効化できる（社内ルールでローカルコピーが禁止されている場合、
または UNC / 共有サーバー上のマクロがコピー元のパスを参照する場合
——`0` を指定すれば元で開ける）。

```python
from comken.toolbox.windows.handler import ExcelComHandler

NAS_PATH = r"\\nas-server\share\data.xlsx"
SHEET = "Sheet1"

# 10 MB 以上は自動でローカルコピー（デフォルト）
with ExcelComHandler(NAS_PATH) as h:
    rows = h.read_rows_as_dicts(SHEET)

# 閾値を変える（50 MB 以上でコピー）
with ExcelComHandler(NAS_PATH, local_copy_threshold_mb=50) as h:
    rows = h.read_rows_as_dicts(SHEET)

# ローカルコピーを無効化（社内ルールで不可・マクロが元パスを参照する場合など）
with ExcelComHandler(NAS_PATH, local_copy_threshold_mb=0) as h:
    rows = h.read_rows_as_dicts(SHEET)
```

ローカルコピーで開いた場合も `save()` は元ファイルへ保存される
（`ExcelWriter.save()` と同じ考え方。一時コピーに保存すると `close()` で消えるため）。
`close()`（with 文の終わり）で一時コピーは自動削除される。

`comken.core.local_copy` コンテキストマネージャは別用途
（COM以外のファイルを NAS 上で読みたい等）で残っている。
**Excel を伴うなら `ExcelComHandler` の自動コピーを使うこと**。
保存先が自動で元ファイルへ戻されるため、`local_copy` で手動コピーすると
`save()` した結果がすべて消える事故が起きる。

---

## Excel

数式の計算結果や VBA マクロが必要な場合は自動で win32com にフォールバックする。

```python
from comken.toolbox.excel import ExcelReader, ExcelWriter

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
rows = CsvReader("data.csv").read_rows()
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
from comken.toolbox.csv import CsvReader

config = Config()
lookup = CsvReader("data.csv").index("注文番号")
mapping = config.受注_MAPPING

with ExcelWriter("data.xlsx") as f:
    matched = f.sheet(SHEET).transfer_by_mapping(
        key_col="受注番号", lookup=lookup, mapping=mapping
    )
    f.save()  # 書き込み後は save() を忘れずに

# ヘッダーがない、または列位置が固定された Excel は列記号版を使う
# どちらのメソッドも「転記元 → 転記先」の向き
column_mapping = {"顧客名": "B", "金額": "C"}
with ExcelWriter("data.xlsx") as f:
    matched = f.sheet(SHEET).transfer_by_letter(
        key_col="A", lookup=lookup, mapping=column_mapping
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
from comken.toolbox.windows import ExcelComHandler

with ExcelComHandler("data.xlsm") as f:
    f.run_macro(MACRO_NAME)
```

### 構造化テーブル

Excel の「テーブル」（リボンの *挿入 > テーブル*）は、**名前の付いたデータ範囲**。
行を足すと範囲が自動で伸びるので、「どこからどこまでがデータか」を行番号で
管理しなくてよくなる。comken では**テーブル名を指定して読み書きできる**。

```
        A          B        C
   1  無関係なメモ
   2
   3
   5    商品      金額     担当     ← 見出し行
   6   りんご      100     田中
   7   みかん      200     鈴木     ← ここまでが「売上」テーブル（C5:E7）
```

シートのどこにあっても、何行あっても、**コードに行番号は出てこない**。

#### 読む

```python
from comken.toolbox.excel import ExcelReader

with ExcelReader("売上.xlsx", tables=True) as f:
    rows = f.read_table("Sheet1", "売上")

# [{"商品": "りんご", "金額": 100, "担当": "田中"},
#  {"商品": "みかん", "金額": 200, "担当": "鈴木"}]
```

見出し行が自動でキーになり、辞書のリストで返る。
人が Excel でテーブルに行を足しても、このコードは直さなくてよい。

| 引数 | 意味 |
|---|---|
| 第1引数 | シート名 |
| 第2引数 | テーブル名（Excel の *テーブルデザイン > テーブル名* で確認できる） |

> **`tables=True` が要る理由**
> `ExcelReader` は既定で読み取り専用モードで開く（大きなブックを速く・省メモリで読むため）。
> このモードでは openpyxl がテーブル定義を読めないので、テーブルを使うときだけ
> 通常モードに切り替える。付け忘れると `TableNotAvailableInReadOnlyError` が出て、
> 対処法がメッセージに表示される。

`ExcelWriter` で開いた場合は `tables` の指定なしで読める（元から通常モードのため）。

```python
with ExcelWriter("売上.xlsx") as f:
    rows = f.read_table("Sheet1", "売上")                       # 読んで
    f.sheet("Sheet1").append_to_table("売上", [{"商品": "ぶどう"}])  # 書く
    f.save()
```

#### 書く

```python
from comken.toolbox.excel import ExcelWriter

rows = [{"商品": "りんご", "金額": 100}, {"商品": "みかん", "金額": 200}]

with ExcelWriter.create("売上.xlsx") as f:            # 新しく作る
    s = f.sheet("Sheet1")
    s.write_table(rows)                               # 見出し + データを書く
    s.add_table("売上", f"A1:B{len(rows) + 1}")       # その範囲をテーブルにする
    f.save()

with ExcelWriter("売上.xlsx") as f:                   # 既存を触る
    s = f.sheet("Sheet1")
    s.replace_table("売上", rows)                     # 中身を入れ替える
    s.append_to_table("売上", [{"商品": "ぶどう", "金額": 300}])  # 行を足す
    s.clear_table("売上")                             # 中身を空にする
    f.save()
```

#### メソッドの使い分け

| したいこと | メソッド | 範囲の扱い |
|---|---|---|
| テーブル名で読む | `read_table(シート名, テーブル名)` | 定義から自動取得 |
| 新しくテーブルを作る | `write_table()` → `add_table()` | `add_table()` で明示 |
| 中身を入れ替える | `replace_table(名前, 行)` | 行数に応じて自動調整 |
| 行を足す | `append_to_table(名前, 行)` | 自動で伸びる |
| 中身を空にする | `clear_table(名前)` | 定義と見出しは残る |

**テーブルの作成・名前変更・削除は人が Excel で行い、プログラムは中のデータだけを触る**のが基本。
`add_table()` を使うのは、プログラムが新規レポートを一から作る場合に限る。
既にあるテーブルを作り直すと、人が設定した書式・数式・スライサーが消える。

#### よくあるつまずき

| 症状 | 原因 | 対処 |
|---|---|---|
| `TableNotAvailableInReadOnlyError` | `ExcelReader` を既定（読み取り専用）で開いた | `ExcelReader(path, tables=True)` |
| `TableNotFoundError` | テーブル名が違う／そのシートに無い | メッセージに出る既存テーブル名の一覧を見る。**シート名も合っているか**確認する |
| `EmptyHeaderCellError` | 見出し行の一部が空 | Excel で見出しの空欄を埋める。列番号がメッセージに出る |
| 空のリストが返る | 見出し行が全て空／データ行が0件 | テーブルの範囲が正しいか Excel で確認する |
| 読んだ値が `=SUM(...)` のような文字列 | テーブル内に数式がある | 下の「数式の扱い」を参照 |
| 人が足した行が読めない | テーブルの範囲外に書かれた | 最終行の**すぐ下**に入力すると範囲に入る。離れた行に書くと入らない |
| 合計行が混ざる | — | 集計行（totalsRow）は自動で除外されるので対処不要 |

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
| キー突合転記が大量行 | ヘッダーがある帳票は `transfer_by_mapping()`、列位置が固定なら `transfer_by_letter()` を使う。通常は高速な openpyxl 版を優先する |

---

## 関連

- [README](../README.md) — ライブラリ全体の概要と環境構築
- [公開 API](自動生成/API.md) — 型ヒント付き署名・引数・戻り値・例外
