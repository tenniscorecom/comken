# CSV 操作

[README（ドキュメントの入口）へ戻る](../README.md)

README の「CSV」から移した、モジュールを使うときの詳しい説明です。

## CSV

```python
from comken.toolbox.csv import CsvReader

ORDER_ID = "A001"
STAFF_NAME = "山田"

reader = CsvReader("data.csv")
# 文字コードは自動判定（UTF-8 → CP932 の順に試す）。明示する場合:
# from comken.constants import Encoding
# CsvReader("data.csv", encoding=Encoding.CP932)

# ヘッダーがある CSV は、列の位置が変わっても壊れない first() を推奨
first_order_id = reader.first("注文番号")  # 最初のデータ行の値。空セルは ""

# ヘッダーがない、または位置で決まっている CSV は cell() で読む
date_text = reader.cell("A2")  # ヘッダー行も1行目として数える
# 複数文字の列記号にも対応: reader.cell("AA2") で27列目を取得
```

data.csv の中身が以下だとする。

```
注文番号,金額,担当者
A001,1000,山田
A002,2000,山田
A003,3000,佐藤
```

```python
# 全行取得（1行 = 1辞書。キーはヘッダー名、値はすべて str）
rows = reader.read_rows()
# → [{"注文番号": "A001", "金額": "1000", "担当者": "山田"},
#    {"注文番号": "A002", "金額": "2000", "担当者": "山田"},
#    {"注文番号": "A003", "金額": "3000", "担当者": "佐藤"}]

# 特定列のみ取得（指定した列だけの辞書になる）
rows = reader.read_rows(columns=["注文番号", "金額"])
# → [{"注文番号": "A001", "金額": "1000"},
#    {"注文番号": "A002", "金額": "2000"},
#    {"注文番号": "A003", "金額": "3000"}]

# キーで1件検索（最初に一致した1行。見つからなければ CsvRowNotFoundError）
row = reader.find("注文番号", ORDER_ID)
# → {"注文番号": "A001", "金額": "1000", "担当者": "山田"}

# 見つからなくても処理を続けたい場合だけ required=False（このときは None が返る）
row = reader.find("注文番号", ORDER_ID, required=False)

# キーで複数行検索（一致した全行。一致なしなら空リスト []）
rows = reader.filter("担当者", STAFF_NAME)
# → [{"注文番号": "A001", ...}, {"注文番号": "A002", ...}]

# 列の値一覧（ヘッダー行は含まない）
amounts = reader.column("金額")
# → ["1000", "2000", "3000"]

# キー列でインデックス化（突合用。キーで行を直接引ける）
lookup = reader.index("注文番号")
# → {"A001": {"注文番号": "A001", "金額": "1000", "担当者": "山田"},
#    "A002": {"注文番号": "A002", "金額": "2000", "担当者": "山田"},
#    "A003": {"注文番号": "A003", "金額": "3000", "担当者": "佐藤"}}

# 同じキーの行が複数あるデータは group_by でまとめる
groups = reader.group_by("担当者")
# → {"山田": [{"注文番号": "A001", ...}, {"注文番号": "A002", ...}],
#    "佐藤": [{"注文番号": "A003", ...}]}
```

`index()` はキーが重複していると `CsvRowDuplicateKeyError` になる。
黙って後の行で上書きすると、突合の結果が静かに変わって気づけないためである。
**重複があるのが普通のデータは `group_by()` を使う。**

**ヘッダー行がない CSV** は `headers` で列名を付ける（1行目からデータとして読まれる）。

```python
# 中身: "A001,1000\nA002,2000\n" （ヘッダーなし）
reader = CsvReader("no_header.csv", headers=["注文番号", "金額"])
reader.read_rows()
# → [{"注文番号": "A001", "金額": "1000"}, {"注文番号": "A002", "金額": "2000"}]
```

### CSV の書き込み（CsvWriter）

```python
from comken.toolbox.csv import CsvWriter

rows = [{"注文番号": "A001", "金額": "1000"}, {"注文番号": "A002", "金額": "2000"}]

# 新規作成（上書き）。親フォルダがなければ自動作成される
writer = CsvWriter("output.csv", fieldnames=["注文番号", "金額"])
writer.write_rows(rows)

# 既存ファイルの末尾に追記（ファイルがなければヘッダー付きで新規作成）
writer.append_row({"注文番号": "A003", "金額": "3000"})
writer.append_rows(rows)

# 文字コードはデフォルト UTF8_SIG（Excel でそのまま開ける）。Shift-JIS が必要なら:
writer = CsvWriter("output.csv", fieldnames=["注文番号"], encoding=Encoding.CP932)
# ※ Encoding.AUTO（読み込み時の自動判定用）を渡した場合は UTF8_SIG として書き込まれる
```

---

## 関連

- [README](../README.md) — ライブラリ全体の概要と環境構築
- [公開 API](自動生成/API.md) — 型ヒント付き署名・引数・戻り値・例外
