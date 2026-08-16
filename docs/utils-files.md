# ファイル操作

[README（ドキュメントの入口）へ戻る](../README.md)

README の「ファイル名・ファイル取得ユーティリティ」から移した、モジュールを使うときの詳しい説明です。

## ファイル名・ファイル取得ユーティリティ

### ファイルの移動・コピー（move_file / copy_file）

shutil を知らなくても使えるラッパー。ルールは共通で
「**dst が既存フォルダならその中へ、それ以外はファイルパス扱い（親フォルダ自動作成）、同名は上書き**」。

```python
from comken.core import copy_file, move_file

move_file("report.xlsx", r"C:\作業\output")            # フォルダの中へ移動
move_file("report.xlsx", r"C:\作業\output\売上.xlsx")   # 名前を変えて移動（out フォルダがなければ作られる）
copy_file("report.xlsx", r"C:\作業\backup")             # コピー（元ファイルは残る。更新日時も保持）
# 返り値は移動・コピー後の Path
```

### ファイル名の組み立て・検索

```python
from comken.core import DateNameBuilder, FileFinder, date_in_name

FOLDER = r"\\nas-server\share"

# 今日の日付付きファイル名を組み立てる
DateNameBuilder("売上レポート").plain()                # → "売上レポート.xlsx"
DateNameBuilder("売上レポート").prefix()               # → "20260711_売上レポート.xlsx"
DateNameBuilder("売上レポート").suffix()               # → "売上レポート_20260711.xlsx"
DateNameBuilder("ログ", ext=".csv").prefix()           # → "20260711_ログ.csv"
DateNameBuilder("月次レポート").prefix(date_format="%Y%m") # → "202607_月次レポート.xlsx"

# ファイル名に含まれる最初の日付を取得（なければ None）
file_date = date_in_name("売上_20260729.csv")            # → datetime.date(2026, 7, 29)

# 今日の日付を含むファイルを取得（見つからなければ FileNotFoundError）
path = FileFinder(FOLDER).today()                      # YYYYMMDD で探す
path = FileFinder(FOLDER).today(date_format="%Y%m")    # YYYYMM で探す

# 日付入りファイルをすべて取得（日付の新しい順。同じ日付なら更新日時の新しい順）
paths = FileFinder(FOLDER).dated()
paths = FileFinder(FOLDER).dated(pattern="*.csv")       # CSV に絞る場合

# フォルダ内で最新のファイルを取得（見つからなければ FileNotFoundError）
# デフォルトは「ファイル名の辞書順で最後」= 日付プレフィックス命名なら名前上の最新。
# コピーや再保存で更新日時が変わっていても影響を受けない
from comken.constants import SortBy

path = FileFinder(FOLDER).latest()
path = FileFinder(FOLDER).latest(pattern="*.csv")        # CSV に絞る場合
path = FileFinder(FOLDER).latest(by=SortBy.UPDATED)      # 更新日時で選びたい場合

# 見つからなくても処理を続けたい場合は required=False（None が返る）
path = FileFinder(FOLDER).today(required=False)
if path is None:
    ...  # スキップ処理など

# dated() は複数件を返すため、required=False で見つからなければ空リスト
paths = FileFinder(FOLDER).dated(required=False)
```

### データ比較（diff_row / diff_rows）

CSV・Excel から読んだ行（辞書）同士の差分を取る。for ループを自分で書かなくてよい。
**CSV の文字列と Excel の数値は同一視される**（`"1000"` と `1000` は差分にならない。
空セルの `None` と `""` も同じ扱い）ので、CSV ↔ Excel をまたいだ比較にそのまま使える。

```python
from comken.core import diff_row, diff_rows

# 1行同士の差分（値が違う列だけ返る）
before = {"注文番号": "A001", "金額": "1000", "担当者": "山田"}
after = {"注文番号": "A001", "金額": 2000, "担当者": "山田"}

diff_row(before, after)
# → {"金額": ("1000", 2000)}
# 差分がなければ {} が返るので、if diff_row(a, b): で「変更あり」を判定できる

# データセット同士の差分（キー列で突合）
before = CsvReader("昨日.csv").read_rows()
with ExcelReader("今日.xlsx") as f:
    after = f.read_rows_as_dicts("Sheet1")

result = diff_rows(before, after, key="社員番号")
result.added    # → after にだけある行のリスト
result.removed  # → before にだけある行のリスト
result.changed  # → 値が変わった行のリスト（RowChange）

for change in result.changed:
    print(change.key)      # → "001"（キー列の値）
    print(change.columns)  # → {"氏名": ("山田", "山田太郎")}（変わった列だけ）
    print(change.before)   # → 変更前の行全体
    print(change.after)    # → 変更後の行全体
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

### 待機（wait）

`time.sleep` の代わりに単位を明示して書ける。「条件が満たされるまで待つ」もループを書かずに済む。

```python
from comken.core import wait

wait.seconds(3)     # 3秒待つ
wait.seconds(0.5)   # 0.5秒待つ
wait.minutes(1)     # 1分待つ

# 条件が True になるまで待つ（デフォルト: 最大60秒・1秒間隔）
ok = wait.until(lambda: Path(r"C:\作業\result.xlsx").exists())
if not ok:
    raise TimeoutError("ファイルが生成されませんでした")

# タイムアウト・間隔を変える場合
ok = wait.until(lambda: 条件, timeout=120, interval=2)
```

### テキスト正規化（normalize / strip_spaces / remove_spaces)

業務データによくある表記揺れ（全角英数・半角カナ・全角スペース）を揃える。
突合キーの正規化に使うと「見た目は同じなのに一致しない」問題を防げる。

```python
from comken.core import normalize, remove_spaces, strip_spaces

normalize("ＡＢＣ１２３")          # → "ABC123"（全角英数 → 半角）
normalize("ｱｲｳ")                  # → "アイウ"（半角カナ → 全角）
normalize("（株）")                # → "(株)"（全角記号 → 半角）

strip_spaces("　山田　太郎　")     # → "山田　太郎"（前後のみ除去。全角スペースも対象）
remove_spaces("０３－１２３４　５６７８")  # → "０３－１２３４５６７８"（全部除去）

# 突合前にキーを正規化する例
lookup = {normalize(k): v for k, v in lookup.items()}
row = lookup.get(normalize(key))
```

### リトライ（retry）

一時的な失敗（クリックが要素に遮られた、ネットワークが一瞬切れた等）を自動でやり直す。

```python
from comken.core import retry

@retry()                     # 3回まで試す（間隔1秒）。全部失敗なら最後の例外が出る
def download_report():
    ...

# 対象の例外を絞る（それ以外は即座にエラー）
from selenium.common.exceptions import ElementClickInterceptedException

@retry(times=5, wait=2, on=(ElementClickInterceptedException,))
def click_submit():
    page.click(page.SUBMIT_BTN)
```

### 処理時間の計測（Timer）

「どこが遅いのか」を調べる。結果は INFO ログに出る。

```python
from comken.core import Timer

with Timer("CSV読み込み"):
    rows = CsvReader("data.csv").read_rows()
# ログ: CSV読み込み: 3.21秒

@Timer("売上集計")            # デコレータでも使える
def aggregate():
    ...

t = Timer("転記処理")
with t:
    ...
print(t.elapsed)              # 経過秒数を値として使える
```

### zip 圧縮・展開（zip_folder / zip_files / unzip）

Windows のエクスプローラーで作られた zip（日本語ファイル名）も文字化けせず展開できる。

```python
from comken.core import unzip, zip_files, zip_folder

zip_folder(r"C:\作業\reports")                       # → C:\作業\reports.zip
zip_files(["a.xlsx", "b.csv"], r"C:\作業\提出用.zip")
unzip(r"C:\作業\data.zip")                           # → C:\作業\data\ に展開
```

---

## 関連

- [README](../README.md) — ライブラリ全体の概要と環境構築
- [公開 API](自動生成/API.md) — 型ヒント付き署名・引数・戻り値・例外
