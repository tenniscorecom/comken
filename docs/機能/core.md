# core（部品）

[README（ドキュメントの入口）へ戻る](../../README.md)

名前を `__all__` で公開している **いちばん浅い** パッケージ・モジュールから取る部品の説明です
（[CONVENTIONS_PYTHON.md §3](../CONVENTIONS_PYTHON.md#3-import-の書き方)）。
`comken` 直下にあるものは `from comken import X`、それ以外は
`from comken.core.dates import today` / `from comken.core.table import Table` /
`from comken.core.timer import Timer` のように書く。
**特定のアプリや外部サービスを触らない**ものだけがここに入る
（Excel・CSV・ブラウザなどは `comken.toolbox`、Windows のフォルダ取得は [Windows 操作](windows.md)）。

## ファイルを探す・動かす

### ファイルの移動・コピー（move_file / copy_file）

shutil を知らなくても使えるラッパー。ルールは共通で
「**dst が既存フォルダならその中へ、それ以外はファイルパス扱い（親フォルダ自動作成）、同名は上書き**」。

```python
from comken.core.files import copy_file, move_file

move_file("report.xlsx", r"C:\作業\output")            # フォルダの中へ移動
move_file("report.xlsx", r"C:\作業\output\売上.xlsx")   # 名前を変えて移動（out フォルダがなければ作られる）
copy_file("report.xlsx", r"C:\作業\backup")             # コピー（元ファイルは残る。更新日時も保持）
# 返り値は移動・コピー後の Path
```

### ファイル名の組み立て・検索

```python
from comken.core.dates import date_in_name, today
from comken.core.files import find_dated_file

FOLDER = r"\\nas-server\share"

# 今日の日付付きファイル名を組み立てる。f-string と ``Path.with_stem()`` のどちらか。
# 拡張子は **名前の文字列に含めて** 書く（引数 ext / extension は廃止）
f"売上レポート_{today():%Y%m%d}.xlsx"           # → "売上レポート_20260711.xlsx"
f"{today():%Y%m_%}月次レポート.xlsx"             # → "202607_月次レポート.xlsx"
# 拡張子なしの名前は FileSuffixMissingError で止める（黙って ".xlsx" は付けない）

# ファイル名に含まれる最初の日付を取得（なければ None）
file_date = date_in_name("売上_20260729.csv")            # → datetime.date(2026, 7, 29)

# 名前を含み、ファイル名の日付が対象日（省略時=今日）のファイルを 1 件返す。
# 探す名前には拡張子を含める。判定は「同じ拡張子（大文字小文字は区別しない）で、`name` の拡張子を
# 除いた本体部分がファイル名の本体部分に **含まれている**（部分一致）」。日付の位置・書式は問わない
path = find_dated_file(FOLDER, "売上レポート.xlsx")               # → 売上レポート_20260711.xlsx など
path = find_dated_file(FOLDER, "売上レポート.csv")                # → 売上レポート_20260711.csv など

# 別日のファイルを探したいときは for_date を渡す
import datetime
path = find_dated_file(FOLDER, "売上レポート.xlsx", for_date=datetime.date(2026, 7, 29))

# 見つからないときは ComkenFileNotFoundError（FileNotFoundError でもある）。
# メッセージにフォルダ・名前・探した日付と対処が出る。
```

> 部分一致なので、`売上.csv` を探すと `売上明細_20260711.csv` も対象になる。
> 紛らわしい名前が同じフォルダにある場合は、探したい名前を長くする
> （`売上明細.csv` を探すなど）。

### データ比較（Table.diff / Table.changes）

CSV・Excel から読んだ行（辞書）同士の差分を取る。for ループを自分で書かなくてよい。
**CSV の文字列と Excel の数値は同一視される**（`"1000"` と `1000` は差分にならない）ので、
CSV ↔ Excel をまたいだ比較にそのまま使える。空は、`Table` に入れる時点で `""` にそろう
（下の「空の値」）ので、空セルの `None` と `""` も同じ扱いになる。

#### 表どうし（`Table.diff(other, key=...)`）

「昨日の表」と「今日の表」をキー列で突合し、追加・削除・変更を一度に取る。
正規化後のキー（`"1000"` と `1000`）がどちらの表でも重複していたら
`TableDuplicateKeyError`（`Table.index()` と同じ例外）で止める。
**黙って後の行で上書きはしない。**

**空キー（`normalize` 後に `""`。`None`・空白だけを含む）は突合しない。**
self の空キー行は `removed`、other の空キー行は `added` に、**元表の行順で**
入る。空でないキーの重複は今まで通り `TableDuplicateKeyError` だが、
**空キーの行は重複検査の対象外**で、同じ表に空キーが何行あってもエラーに
ならない。Excel の ID が空欄の行が複数あるケースを自然に受け流せる。

```python
from comken.toolbox.csv import CSV

with CSV("昨日.csv") as csv_file:
    yesterday = csv_file.read()  # Table が返る
with CSV("今日.csv") as csv_file:
    today = csv_file.read()

result = yesterday.diff(today, key="社員番号")
result.added    # → today にだけある行（Table）
result.removed  # → yesterday にだけある行（Table）
result.changed  # → 値が変わったセル（Table。1 行 = 1 セルの変更）

# result.changed の中身（1 つの行で 2 列変われば 2 行になる）
# 社員番号 | 列   | 変更前 | 変更後
# 001      | 氏名 | 山田   | 山田太郎
# 001      | 部署 | 営業   | 企画

for cell in result.changed:
    print(cell["社員番号"], cell["列"], cell["変更前"], "→", cell["変更後"])
```

3 つとも `Table` なので `filter` / `select` / `count` や CSV・Excel への書き出しなど、
Table 標準の操作が直接使える。`result.changed` の `社員番号` の値は、正規化後の文字列
（`"001"`）。変更前・変更後の行まるごとが必要なら、元の表を `yesterday.index("社員番号")`
で引く。専用のクラスや `(前, 後)` のタプルは返さない（前と後は列名で読める）。
キー列の名前が `列` / `変更前` / `変更後` と重なっていると `TableError`。

#### 同じ表の中の履歴（`Table.changes(key=..., order_by=...)`）

社員番号ごとに履歴が並んでいるとき、`order_by`（変更時刻など）で
昇順に並べてから隣り合う行を比べる。同じ社員番号でも変更時刻が
時系列順でないと誤判定になるため、`order_by` は省略しない方が安全。

`order_by` を**省略すると、表の並び順のまま**比べる（入力順を信用する場合）。
比較する列から `key` と `order_by` の列は除く（変更時刻は毎回違うので、
含めると全部が「変わった」になる）。

```python
history = Table(
    ["社員番号", "変更時刻", "部署", "役職"],
    [
        {"社員番号": "1001", "変更時刻": "2026-09-03", "部署": "総務", "役職": "主任"},
        {"社員番号": "1001", "変更時刻": "2026-09-01", "部署": "営業", "役職": "一般"},
        {"社員番号": "1001", "変更時刻": "2026-09-02", "部署": "営業", "役職": "主任"},
    ],
)

changed = history.changes(key="社員番号", order_by="変更時刻")
# Table.diff() の changed と同じ形（1 行 = 1 セルの変更）。変更時刻は変更後の行のもの
# 社員番号 | 変更時刻   | 列   | 変更前 | 変更後
# 1001     | 2026-09-02 | 役職 | 一般   | 主任
# 1001     | 2026-09-03 | 部署 | 営業   | 総務
```

`order_by` の列に空（`""`）の行がある、または値の型が混ざって
いて比較できない（`TypeError`）ときは `TableError` で止める。

**空キー（`normalize` 後に `""`）の行は対象外**で、**そもそも比べない**
（`Table.diff()` / `Table.transfer_from()` と同じ規則）。空キーが複数あっても
`TableDuplicateKeyError` にはならず、空キー行の `order_by` が空でも
エラーにしない。


### 待機（wait）

`time.sleep` の代わりに単位を明示して書ける。「条件が満たされるまで待つ」もループを書かずに済む。

```python
from comken.core.wait import wait_until
from comken.core.wait import wait_seconds

wait_seconds(3)     # 3秒待つ
wait_seconds(0.5)   # 0.5秒待つ

# 条件が True になるまで待つ（デフォルト: 最大60秒・1秒間隔）
ok = wait_until(lambda: Path(r"C:\作業\result.xlsx").exists())
if not ok:
    raise TimeoutError("ファイルが生成されませんでした")

# タイムアウト・間隔を変える場合
ok = wait_until(lambda: 条件, timeout=120, interval=2)
```

### セル値→日付（parse_cell_date）

Excel の日付列は型がバラバラで来る（`datetime.datetime` / `datetime.date` / 文字列）のを
`datetime.date` に揃えて返す関数。

```python
from comken.core.dates import parse_cell_date

parse_cell_date(datetime.datetime(2026, 4, 22, 12, 30))  # → date(2026, 4, 22)
parse_cell_date("2026/04/22")                             # → date(2026, 4, 22)
parse_cell_date("2026年04月22日")                          # → date(2026, 4, 22)
parse_cell_date("2026/04/22 00:00:00")                    # → date(2026, 4, 22)
parse_cell_date("日付ではない")                            # → None
parse_cell_date(None)                                     # → None
```

新しい書式を足すときは `comken/core/dates/parse.py` の `_DATE_TEXT_FORMATS` に
タプル要素を追加する。

`month_start` / `month_end` / 年度 (`fiscal_year`) の使い方は
[dates.md](dates.md) を参照。日付書式の変換は `strftime` / `strptime` を
そのまま使う（[dates.md「書式の変換」](dates.md#書式の変換)）。

### テキスト正規化（normalize / remove_spaces)

業務データによくある表記揺れ（全角英数・半角カナ・全角スペース）を揃える。
**`Table.diff()` と `Table.transfer_from()` は、キー・値を比べるときに、内部でこの `normalize` を使う**
（`"1001"` と `1001.0`、`Ａ１` と `A1`、前後の空白の違いは同じとみなす）。
自分で突合するコードを書くときも、この関数でそろえてから比べると「見た目は同じなのに一致しない」
問題を防げる。

元に戻せない変換（NFKC）なので、**書き戻すデータには使わず、比べるときの鍵にだけ使う**。
Python の中の文字は NFKC にそろえる方針で、Excel の `ASC` / `JIS` 関数とは別の変換
（NFKC は英数字を半角、カナを全角にする。`ASC` は両方半角、`JIS` は両方全角）。

```python
from comken.core.text import normalize, remove_spaces

normalize("ＡＢＣ１２３")          # → "ABC123"（全角英数 → 半角）
normalize("ｱｲｳ")                  # → "アイウ"（半角カナ → 全角）
normalize("（株）")                # → "(株)"（全角記号 → 半角）
normalize(1000.0)                  # → "1000"（整数値の小数は整数に。Excel の数値 ↔ CSV の文字列）

# 前後のスペース除去は組み込みの str.strip() を使う（全角スペース U+3000 も取れる）
"　山田　太郎　".strip()           # → "山田　太郎"
remove_spaces("０３－１２３４　５６７８")  # → "０３－１２３４５６７８"（全部除去）

# 突合前にキーを正規化する例
lookup = {normalize(k): v for k, v in lookup.items()}
row = lookup.get(normalize(key))
```

### 管理表セルの真偽判定（`is_enabled_mark`）

Excel / CSV の管理表（レポート管理表・スケジュール管理表など）の
「有効」列の値を 1 か所で判定する。 `soql-collector` やダウンローダーが
それぞれで重複していた ``"○"`` / ``"有効"`` / ``"yes"`` 判定を 1 箇所に
まとめるためのもの。

```python
from comken.core.text import is_enabled_mark

is_enabled_mark("有効")      # → True
is_enabled_mark("○")         # → True
is_enabled_mark("YES")       # → True
is_enabled_mark("1")         # → True（Excel セルでは文字列として来る）
is_enabled_mark(1)           # → True（int で来た場合）
is_enabled_mark(True)        # → True（bool そのまま）
is_enabled_mark("無効")      # → False
is_enabled_mark("×")         # → False
is_enabled_mark("no")        # → False
is_enabled_mark("0")         # → False
is_enabled_mark(None)        # → False
```

真とみなす語（前後の半角・全角空白を除き、大文字小文字は区別しない）:
`有効` / `○` / `o` / `yes` / `1` / `on` / `はい` / `true`。
`bool` がそのまま来たら `bool` を返し、 `int` は `1` だけ True。
それ以外（空文字 / `×` / `無効` / `None` など）は False。

> **config.ini の ``bool`` 変換は変えない。** `is_true_word("1") is False`
> のまま（config.ini の `1` を bool にすると整数 `1` と区別できなくなる
> ため）。「○/×」運用を続ける管理表側でだけ `is_enabled_mark` を使う。

### リトライ（retry）

一時的な失敗（クリックが要素に遮られた、ネットワークが一瞬切れた等）を自動でやり直す。

```python
from comken.core.retry import retry

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
from comken.core.timer import Timer

with Timer("CSV読み込み"), CSV("data.csv") as csv_file:
    rows = csv_file.read()
# ログ: CSV読み込み: 3.21秒

@Timer("売上集計")            # デコレータでも使える
def aggregate():
    ...

t = Timer("転記処理")
with t:
    ...
print(t.elapsed)              # 経過秒数を値として使える

# ログ文言を変えたいときは message を渡す（{name} / {elapsed} が使える）
with Timer("CSV読み込み", message="{elapsed} [{name}]"):
    ...
# ログ: 3.21秒 [CSV読み込み]

# 経過時間の書式を変えたいときは time_format を渡す
# ``datetime.strftime`` と全く同じ書き方。``%H`` / ``%M`` / ``%S`` などの
# 書式がそのまま使える（``%I`` / ``%p`` / ``%%`` なども可）。
# 経過秒は整数秒に四捨五入（0.5 は切り上げ）してから整形する。
with Timer("CSV読み込み", time_format="%H:%M:%S"):
    ...
# ログ: CSV読み込み: 00:00:03

# 既定（time_format=None）は小数2桁＋「秒」の形
with Timer("CSV読み込み"):
    ...
# ログ: CSV読み込み: 3.21秒
```

### デバッグ用 measure（`comken.debug()` 中だけログ）

`Timer` は**常に**ログが出る。`measure` は `with comken.debug():` ブロック内でのみ
DEBUG ログが出る。普段は無音で、止まったときだけ `with comken.debug():` を
`main.py` で `main()` を囲む形に直して再実行すれば、どの処理で止まったかが
後から分かる。

```python
from comken.core.timer import measure

@measure
def build_report():
    ...
```

ログは関数ごとに次の2行（例外時は別の1行）になる:

```
DEBUG Excel.save: 開始
DEBUG Excel.save: 完了 1.234秒
```

「どのファイルで止まったか」を知りたいときは呼び出し側がログへ出す。

### ファイル出現待ち（wait_for_file）

業務自動化で頻出する「共有サーバーから CSV が落ちてくるのを待つ」「RPA 基盤が
ファイルを置くのを待つ」を 1 関数で済ませる。

```python
from comken.core.wait import wait_for_file

path = wait_for_file(
    folder=r"\\server\\share\\input",
    name_pattern="data_*.csv",
    timeout=60.0,        # 最大待機秒数 (既定 60 秒)
    poll_interval=1.0,   # 再検索間隔 (既定 1 秒)
)
# → 見つかったファイルのうち mtime が最新の Path を返す
```

失敗の理由は 2 つに分かれる。**どちらなのかがメッセージで分かる。**

| 状況 | 例外 | いつ |
|---|---|---|
| ファイルが `timeout` 秒来なかった | `FileNotFoundError`（ファイル名を出す） | `timeout` 後 |
| 監視するフォルダが無い | `FileNotFoundError`（「監視するフォルダがありません」） | **待たずに即座** |
| `folder` にファイルを渡した | `NotADirectoryError` | 待たずに即座 |

### 書き込み完了待ち（wait_until_stable / stable_for）

ファイルが「存在する」ことと「書き終わっている」ことは別（作成直後のファイルは
書き込み途中でも `is_file()` が True になる）。他システムが共有サーバーへ置きにくる
ファイルを読むときは、書き込み完了まで待つ。

```python
from comken.core.wait import wait_for_file, wait_until_stable

# 見つけたら、そのまま完了まで待つ
path = wait_for_file(folder, "data_*.csv")
path = wait_until_stable(path)

# すでにパスが分かっているとき
path = wait_until_stable(r"\\server\share\in\data.csv", stable_for=2.0)
```

サイズと更新時刻を見て、`stable_for` 秒どちらも変わらなければ書き終わったとみなす。
`timeout` は **`wait_for_file` と `wait_until_stable` で別々に指定する**
（後者に合算されることはない）。

| 状況 | 例外 |
|---|---|
| ファイルが無い / 待っている間に消えた | `FileNotFoundError` |
| ファイルは有るが `timeout` までに書き終わらない | `TimeoutError` |

`find_dated_file()` は1 回探すだけなので「無ければ待つ」は `wait_for_file()` を使う。

### zip 圧縮・展開（zip_folder / zip_files / unzip）

Windows のエクスプローラーで作られた zip（日本語ファイル名）も文字化けせず展開できる。

```python
from comken.core.files import unzip, zip_files, zip_folder

zip_folder(r"C:\作業\reports")                       # → C:\作業\reports.zip
zip_files(["a.xlsx", "b.csv"], r"C:\作業\提出用.zip")
unzip(r"C:\作業\data.zip")                           # → C:\作業\data\ に展開
```

---

## 表データ（`Table`） — よく使う操作

### 空の値は `""`（`None` は持たない）

`Table` に入れた値のうち `None` は **空文字 `""` にそろう**（`Table(...)`、`append`、
`CSV` / Excel / Access / Salesforce から読んだ値のどれでも同じ）。
CSV は空欄が `""`、Excel / Access は空が `None` で返ってくるので、`Table` の入口で1回だけ
そろえて、「`None` と `""` のどちらで来るか」を利用側が気にしなくて済むようにしている。
`types=` の変換関数が受け取る値も、`None` ではなく `""` になる。

`CSV.read()` / `ExcelTable.read()` が返す `Table` は **イミュータブルに見えるが
内部は行を保持している**。表データを扱うときに覚えておく操作をまとめる
（網羅は公開 API を参照）。

```python
from comken.core.table import Table

table = Table(["ID", "氏名"], [{"ID": "001", "氏名": "山田"}, {"ID": "002", "氏名": "鈴木"}])

# 添字で行を取る（**コピー**なので書き換えても Table は変わらない）
row = table[0]               # → {"ID": "001", "氏名": "山田"}
row["氏名"] = "変更"          # table[0] は変わらない

# 全行を回す（イテレータもコピーを返す）
for row in table:
    print(row["氏名"])

# 行数
len(table)                   # → 2

# 全行を list[dict] で取り出す（コピー）
rows = table.to_rows()
```

表全体は `Table`、1 行は `Row`（実体は `dict[str, Any]` の別名）です。`table[n]` /
`for row in table` / `to_rows()` / `iter_rows()` など、行を返すものの注釈は `Row` で、
型の名前が表と行で分かれています（実行時の動作は `dict` のままです）。

注釈に使う共通の型は、`comken.core.types` から 1 行で import します。

```python
from comken.core.types import Row, TypeMap, Value

def total(rows: list[Row]) -> int: ...       # 表の 1 行
cells: dict[str, Value] = {"金額": 1000}      # セルの値（str / int / float / bool / datetime）
converters: TypeMap = {"金額": int}           # types= に渡す「列名 → 変換する関数」
```

| やりたいこと | API |
|---|---|
| `n` 行目を 1 件取りたい | `table[n]` |
| 全行を回したい | `for row in table:` |
| 行数 | `len(table)` |
| `list[Row]`（`list[dict]`）で受け取る | `table.to_rows()` |
| 全行を置き換え | `table.replace(rows)` |
| 1 行 / 複数行を末尾に追加 | `table.append(row)` / `table.append(rows)` |

`Table.transfer_from()` の `result.only_in_read` / `result.only_in_write` はどちらも入力のコピーの
`Table`。`result.table` に `append()` して新規行として追加できる
（[Table.transfer_from()（転記）](#tabletransfer_from転記) 参照）。

### `Table.transfer_from()`（転記）

CSV / Excel / Access などを ``Table`` に統一して読む。CSV は ``CSV.read()``、
Excel は ``Excel.data_sheet().table().read()`` で ``Table`` を取得し、転記は
メソッド ``Table.transfer_from()`` 1 回の呼び出しで済ませる。
別に ``transfer`` を import しなくても ``Table`` から直接呼べ、
``excel_table.transfer_from(csv_table, ...)`` と書けて
「Excel の表が CSV の表から転記を受ける」と向きが読める。

```python
from comken.core.table import Table

result = destination.transfer_from(
    source,
    mapping={"取引先": "顧客名", "金額": "請求額"},
    read_key="注文番号", write_key="注文番号",
)
result.table          # 転記後の write（write と同じ列・同じ行順・同じ行数の新しい Table）
result.only_in_read   # write に対応が無い read の行（Table・read の列構成）
result.only_in_write  # read に対応が無い write の行（Table・write の列構成・転記前の値）
result.matched_count  # キーが一致した組の数（where の結果と無関係）
result.transferred_count  # そのうち where=True で実際に転記した組の数
```

戻り値は `TransferResult`。**入力の ``read`` / ``write`` は変更しない**。
保存は CSV / Excel の ``with`` を正常終了した時に行う。

**``where=`` で追加の条件を指定できる**。呼び出し側は判定だけ書く
（行を直す処理は書かない。ログは可）。`Callable[[Row, Row], bool]` で
`True` のときだけ転記する。受け取るのは `Row` のコピー（書き換えても
結果にも入力にも影響しない）。`where` は matched な組に対して
1 組につき 1 回だけ呼ばれる（matched だが転記されなかった組は
`matched_count` には入るが `transferred_count` には入らず、
`only_in_*` にも入らない）。

```python
result = destination.transfer_from(
    source, mapping,
    read_key="注文番号", write_key="注文番号",
    where=lambda read_row, write_row: read_row["金額"] > 0,
)
```

**未一致の行は ``result.only_in_read`` / ``result.only_in_write`` に取り出される**。
それぞれ `Table` なので、`result.table.append(...)` で新規行として追加する、
`result.table.replace([...])` の内包表記でセルを更新する、`Table.filter()` で
条件に合う行だけ残す、という Table 標準の操作がそのまま使える。

**空キー（``""``。``None`` は Table に入れた時点で ``""`` になる）は突合対象外**。
``0`` / ``False`` は空ではない。空キーは read / write のどちらでも ``only_in_*`` 側
へ流れるため、write 側に空キーが複数あっても ``TableError`` にはならない。

**キーは ``normalize`` でそろえてから比べる**（``Table.diff()`` と同じ規則）。
CSV の ``"1001"`` と Excel の ``1001.0``、全角の ``Ａ１`` と半角の ``A1``、
前後の空白の違いは同じキーとして突合する。突合に使うだけで、転記するデータは
変えない（ただし ``write.types`` の変換だけは転記した値に 1 回かける）。先頭ゼロ付きの
文字列（``"0001"``）は数値の ``1`` と同じにならない。空白だけのキーは空キー。

**正規化後のキーが重複していたら ``TableDuplicateKeyError``**（`read` 側・`write` 側の
どちらも。``Table.index()`` / ``Table.diff()`` と同じ例外）。どの行が勝つかを黙って決めて
上書きしてしまうのを防ぐため。複合キーの場合は ``"カラム1,カラム2"`` の形でメッセージに出る。

**1 対多は事前に ``group_by()`` で 1 行にまとめてから渡す**。`read` 側に同じキーの行が複数
ある場合（明細など）は、``group_by()`` で合計・先頭の選択などをしてから `read` に渡す。
`Table.transfer_from()` 自身は集約をしない。

**転記した値には、転記先列の ``types=`` の変換を 1 回かける**。CSV の ``"1000"`` が文字列の
まま `int` 列に入るのを防ぐため。転記しなかった行・列には変換をかけない。転記先の列に
``types=`` が無ければ変換しない（型は推測しない）。変換できない値は ``TableError``。

**セルの値は ``str`` / ``int`` / ``float`` / ``bool`` / ``datetime`` などの不変の値
であること** を前提とする。``list`` や ``dict`` など変更可能な値をセルに入れた場合、
浅いコピーによる共有は保証しない。

---

## 設定・状態・ログ・実行モード

### 実行モード（バージョン / デバッグ / dry-run）

実行モードの切り替えは **`with dry_run():` / `with debug():` の context manager**。
**設計上の理由**（`config.ini` を読まない理由・旧 `[RUN]` セクションの廃止経緯など）は
[**設計書「4. 設定と実行モード」**](../ARCHITECTURE.md#4-設定と実行モード)と [**HISTORY.md**](../HISTORY.md#1-設定と非機密情報の扱い)を参照。

```python
import comken

comken.__version__        # → "1.3.0"

# デバッグモード: `with debug():` ブロック内でのみ @measure が DEBUG ログを出す。
with comken.debug():
    run()

# dry-run モード: 外部に影響する操作を実行せず、内容だけ [DRY-RUN] 付きで INFO ログに出す。
# 読み取り（CSV・Excel の読み込み）は通常どおり実行される
with comken.dry_run():
    run()
```

自作関数の出入りを同じ仕組みで記録できる（デバッグモード中だけログが出る）:

```python
from comken.core.timer import measure

@measure
def build_report():
    ...
```

`@measure` は**関数名（qualname）だけ**をログに出す。引数・戻り値は出さない
（DPAPI のトークン・client_secret・パスワードを扱うため、汎用デコレータが
自動で引数を出す形になっていると、いつか秘密の値がログへ載る危険があるため）。
「どのファイルで止まったか」を知りたいときは、呼び出し側が処理対象をログに出す。

雛形プロジェクトでは `with comken.debug():` を `main()` を囲む形で
`main.py` に書き、止めたい処理単位で on/off する（`config.ini` の旧 `[RUN]` セクションは
廃止済みのため、書いても効きません。詳細は[**HISTORY.md**](../HISTORY.md#1-設定と非機密情報の扱い)）。

---

### Config

`config.ini` を `config.SECTION.KEY` の形式で読み込む。

**基本の使い方**（`src/config.py` は不要。エディタ補完も効く）:

```python
from comken import config

# 初回アクセス時にカレントディレクトリの config.ini を1度だけ読む（遅延読み込み）
folder = config.REPORT.OUTPUT_FOLDER
path = config.FILES.INPUT_FOLDER / "支店A.csv"

# config.ini が別の場所にあるときは Config(path) を直接呼んで使う
from comken.core.config import Config

local_config = Config(r"C:\作業\config.ini")
folder = local_config.REPORT.OUTPUT_FOLDER
```

> **補完（Pylance）:** config を初めて読むと、config.ini から補完用スタブ
> `typings/comken/core/`（config.pyi）と `typings/comken/__init__.pyi` が自動生成される。
> VS Code + Pylance で `config.SECTION.KEY` が型付き補完される（typings/ は .gitignore 推奨）。
> `Config()` を一度呼ぶだけで、スタブは自動更新される。

明示的にインスタンスを持ちたい場合（テストや複数 ini の読み分けに）:

```python
from comken import Config

config = Config()                      # カレントディレクトリの config.ini
config = Config("path/to/config.ini")  # パスを指定する場合
```

```ini
; config.ini（プロジェクト固有の非機密設定を書く）。
; 命名・配置の規約（セクション名・キー名は大文字、パスは config.ini からの相対パスが既定）は
; [**CONVENTIONS.md**](../CONVENTIONS.md#5-configini-の書き方) を参照。

[REPORT]
OUTPUT_FOLDER = ./output
TEMPLATE_PATH = \\nas-server\templates\template.xlsx
```

```python
config.REPORT.OUTPUT_FOLDER # → Path
config.REPORT.TEMPLATE_PATH # → Path
```

**列の対応は config.ini ではなく、利用側のコードの先頭に定数で書く**（どこで動かしても同じ値で、
変更の履歴を git に残すため）。対応表は**見出し名**で書き、列記号（`X` / `AB` …）で依頼が
来たら見出し名に直す。列記号で書くと、列が挿入されたときに黙ってずれて気付けないため。

```python
TRANSFER_MAPPING = {"お名前": "氏名"}
```

**値の型変換ルール:**

| config.ini の値 | 返る型 |
|---|---|
| `true` / `false`（大文字小文字問わず） | bool に自動変換 |
| `yes` / `no` / `on` / `off` | **変換しない**（str のまま） |
| `[a, b, c]` | list[str] に自動変換 |
| 整数（`10` など） | int に自動変換 |
| 小数（`1.5` など） | float に自動変換 |
| 絶対パス（`C:\...` / `\\...` / `/...`） | Path に自動変換 |
| その他の文字列 | str のまま |

`true` / `false` 以外の `yes` / `on` / `1` / `0` を bool に変換しないのは、
`1` が「数値の1」なのか「ON の意味」なのか曖昧になる事故を避けるため。
数値を文字列として使いたい場合（シート名 `"2024"` など）はコード側で `str()` に変換する。

**リスト値は `[...]` で囲んで書く**（カンマ区切り。改行区切りも可）:

```ini
[REPORT]
TARGET_SHEETS = [支店A, 支店B, 集計]
ONE_SHEET = [支店A]
```

```python
config.REPORT.TARGET_SHEETS   # → ["支店A", "支店B", "集計"]
config.REPORT.ONE_SHEET       # → ["支店A"]（1要素でもリスト）
```

`[...]` で囲むのは「1要素のリスト」と「ただの文字列」を区別するため
（カンマの有無だけで判定すると、リストを1件に減らした途端に文字列になり、
for ループが文字単位になる事故が起きる）。

**エディタの補完候補（型スタブの自動生成）:**

属性は実行時に動的に作られるため、そのままではエディタが `config.REPORT.` の先を補完できない。
そのため config を初めて読むと、config.ini から補完用スタブ `typings/comken/`
（config.pyi + `__init__.pyi`）が自動生成される。VS Code + Pylance がこれを読み、
セクション・キーが型付きで補完される（config.ini を変更すると次の実行で更新される）。

まだ一度も実行していない状態で先にスタブだけ作りたい場合は `from comken import config`
を1度実行すれば自動生成される（`Config()` 初期化時に `typings/comken/` が更新される）。

生成された `typings/` は手で編集せず、`.gitignore` に含める（自動生成物）。

なお**ブラウザの設定は config.ini には書かない**。`BrowserOptions` のインスタンス
（`src/browser_options.py`）で行う（Browser を参照）。

---

### State

人が書く固定の設定は `config.ini`、プログラムが次回へ持ち越す状態は `state.ini` と
使い分ける。人が調整した設定をプログラムが上書きする事故を防ぐため、両者は混ぜない。

```python
from comken.core.state import State

state = State()                         # 実行フォルダ直下の state.ini
last_file = state.get("LAST_FILE")     # 無ければ None
position = state.get("POSITION", 0)    # 既定値も指定できる
state.set("LAST_FILE", "data.csv")    # その場で保存
```

`state.ini` が無い初回実行は空の状態で続行する。値は文字列・数値・bool・文字列リストの
型を保って読み戻せる。壊れたファイルは続きの位置を失わないよう、初回扱いにせずエラーで止まる
（dry-run 中の `set()` の扱いなど、詳細は[**設計書「4. 設定と実行モード」**](../ARCHITECTURE.md#4-設定と実行モード)）。

実際に保存される内容:

```ini
[STATE]
LAST_FILE = "data.csv"
POSITION = 42
```

---

### Logger

社内環境では `setup_logging()` に環境クラスを渡し、root logger を設定する。
二重呼び出し時の挙動や `LOG_ROOT` / `LOG_FOLDER_NAMES` の二段構成など、詳細は
[**HISTORY.md**](../HISTORY.md#9-ロギング)を参照。

```python
from comken.core.logger import Backoffice, setup_logging

setup_logging(Backoffice)
```

RPA 基盤を通さず単体実行するときは、`setup_local_logging()` で root logger を設定する。
`setup_local_logging()` は `None` を返さないので、logger は `getLogger(__name__)` で取る。

```python
# main.py
from comken import comken_logger

comken_logger.setup_local_logging()  # コンソールと logs/local-YYYY-MM-DD.log（UTF-8）へ出力
logger = logging.getLogger(__name__)
logger.info("処理開始")
```

```python
# src/ 以下のモジュール
import logging

logger = logging.getLogger(__name__)
logger.info("CSV読み込み完了: %d件", len(rows))
```

---

## 関連

- [README](../../README.md) — ライブラリ全体の概要と環境構築
- 公開 API — 型ヒント付き署名・引数・戻り値・例外（`python tools\export_for_chat.py` で生成。git では管理しない）
