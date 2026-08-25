# core（部品）

[README（ドキュメントの入口）へ戻る](../README.md)

`from comken.core import ...` で取る部品の詳しい説明です。
**特定のアプリや外部サービスを触らない**ものだけがここに入る
（Excel・CSV・ブラウザなどは `comken.toolbox`、Windows のフォルダ取得は [Windows 操作](windows.md)）。

## ファイルを探す・動かす

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
from comken.core import DateNameBuilder, DateFileFinder, date_in_name, dates_in_name

FOLDER = r"\\nas-server\share"

# 今日の日付付きファイル名を組み立てる
# 拡張子は **名前の文字列に含めて** 渡す（引数 ext / extension は廃止）
DateNameBuilder("売上レポート.xlsx").prefix()               # → "20260711_売上レポート.xlsx"
DateNameBuilder("売上レポート.xlsx").suffix()               # → "売上レポート_20260711.xlsx"
DateNameBuilder("ログ.csv").prefix()                       # → "20260711_ログ.csv"
DateNameBuilder("月次レポート.xlsx").prefix("{:%Y%m}_")    # → "202607_月次レポート.xlsx"
# 拡張子なしの名前は FileSuffixMissingError で止める（黙って ".xlsx" は付けない）

# ファイル名に含まれる最初の日付を取得（なければ None）
file_date = date_in_name("売上_20260729.csv")            # → datetime.date(2026, 7, 29)
# ファイル名に含まれる日付を **すべて** 出現順で取得（なければ空リスト）
all_dates = dates_in_name("一覧_20260801_20260831.xlsx") # → [date(2026, 8, 1), date(2026, 8, 31)]

# 今日の日付を含むファイルを取得（見つからなければ FileNotFoundError）
# 探す名前には拡張子を含める。`stem + YYYYMMDD + 拡張子` に一致するファイルを返す
path = DateFileFinder(FOLDER).prefix("売上レポート.xlsx")               # → 売上レポートYYYYMMDD.xlsx
path = DateFileFinder(FOLDER).prefix("売上レポート.csv")                # → 売上レポートYYYYMMDD.csv
# name 側に "{:%Y-%m-%d}" のような日付書式を書けば、その位置へ日付が入る
path = DateFileFinder(FOLDER).prefix("{:%Y-%m-%d}_月次.xlsx")           # → 2026-07-29_月次.xlsx

# 別日のファイルを探したいときは for_date を渡す
import datetime
path = DateFileFinder(FOLDER, for_date=datetime.date(2026, 7, 29)).prefix("売上レポート.xlsx")

# 見つからなくても処理を続けたい場合は required=False（None が返る）
path = DateFileFinder(FOLDER).prefix("売上レポート.xlsx", required=False)
if path is None:
    ...  # スキップ処理など

# 日付付きファイルを全件、日付の新しい順で取得（見つからなければ空リスト）
# 第1引数の接頭辞には拡張子を含めてもよく、含めなくてもよい（含める場合は絞り込みになる）
paths = DateFileFinder(FOLDER).dated("売上レポート.xlsx")                  # → [売上レポート20260730.xlsx, 売上レポート20260729.xlsx, ...]
paths = DateFileFinder(FOLDER).dated("売上レポート.csv")
# `prefix()` と違い、`prefix` 内の日付書式（{:%Y-%m-%d} 等）は解釈しない
# `for_date` を指定しても結果は同じ（フォルダ内の全件が対象）
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
with CSV("昨日.csv") as csv_file:
    before = csv_file.read()
with Excel("今日.xlsx") as f:
    after = f.read("Sheet1")

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


### 待機（wait）

`time.sleep` の代わりに単位を明示して書ける。「条件が満たされるまで待つ」もループを書かずに済む。

```python
from comken.core import wait_seconds, wait_until

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

Excel の日付列は **セル値の型がバラバラ**で来る（`datetime.datetime` /
`datetime.date` / 文字列）。 それぞれを `datetime.date` に揃え、読めなかった値は
`None` を返す（例外にはしない）。 「読めない行は件数だけ `WARNING` に出して集計から
外す」業務運用に向いている。

```python
from comken.core import parse_cell_date

parse_cell_date(datetime.datetime(2026, 4, 22, 12, 30))  # → date(2026, 4, 22)
parse_cell_date("2026/04/22")                             # → date(2026, 4, 22)
parse_cell_date("2026年04月22日")                          # → date(2026, 4, 22)
parse_cell_date("2026/04/22 00:00:00")                    # → date(2026, 4, 22)
parse_cell_date("日付ではない")                            # → None
parse_cell_date(None)                                     # → None
```

受け付ける書式は `clock.py` の `_DATE_TEXT_FORMATS` に固定。 新しい書式を足すときは
**ここにタプル要素を追加する**。 内閣府祝日 CSV の `_parse_date` は配布フォーマットの
制約で 2 形式に固定した別口なので、 緩めた場合に「内閣府以外のファイルを取り違えても
気付かない」事故を防ぐために揃えていない。

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
```

### デバッグ用 measure（`comken.debug()` 中だけログ）

`Timer` は**常に**ログが出る。`measure` は `with comken.debug():` ブロック内でのみ
DEBUG ログが出る。普段は無音で、止まったときだけ `with comken.debug():` を
`main.py` で `main()` を囲む形に直して再実行すれば、どの処理で止まったかが
後から分かる。

```python
from comken.core import measure

@measure
def build_report():
    ...
```

ログは関数ごとに次の2行（例外時は別の1行）になる:

```
DEBUG Excel.save: 開始
DEBUG Excel.save: 完了 1.234秒
```

主目的は「どの処理で止まったか」を特定すること。終了時にしかログを出さないと、
止まった処理の痕跡は永久に残らない。**関数名だけ**を出し、引数・戻り値は出さない
（DPAPI のトークン・client_secret などの秘密の値がログへ載る危険があるため）。
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

フォルダの不在を即座に失敗させるのは、`Path.glob()` が存在しないフォルダでも
例外を出さず空を返すため。区別しないと「共有サーバーが切れている」「パスの打ち間違い」も
「ファイルがまだ来ていない」と同じ形で 60 秒後に失敗し、原因が分からなくなる。
待っている間にフォルダごと消えた場合も、`timeout` 到達時にそちらを知らせる。

### 書き込み完了待ち（wait_until_stable / stable_for）

**ファイルが「存在する」ことと「書き終わっている」ことは別。** 作成直後の
ファイルは書き込み途中でも `is_file()` が True になるので、そのまま読むと
途中までの内容を掴むことがある。他システムが共有サーバーへ置きにくる
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

**サイズと更新時刻でしか判断できないので確実ではない。** 書き込み側が
`stable_for` より長く止まると、途中でも「書き終わった」と判定する。
不安定な共有フォルダでは `stable_for` を長めに取る。

**書き込み側を自分で書けるなら、この関数より「別名で書いてから rename する」
ほうが確実**（`core/files` の atomic 系がその形）。rename は一瞬で終わるので、
読む側が途中の状態を見ることがない。`wait_until_stable` は**書き込み側に
手を出せないとき**の手段。

`DateFileFinder.prefix()` は1 回探すだけなので「無ければ待つ」はこちらを使う。

### zip 圧縮・展開（zip_folder / zip_files / unzip）

Windows のエクスプローラーで作られた zip（日本語ファイル名）も文字化けせず展開できる。

```python
from comken.core import unzip, zip_files, zip_folder

zip_folder(r"C:\作業\reports")                       # → C:\作業\reports.zip
zip_files(["a.xlsx", "b.csv"], r"C:\作業\提出用.zip")
unzip(r"C:\作業\data.zip")                           # → C:\作業\data\ に展開
```

---

## 表データ（`Table`） — よく使う操作

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
table.count()                # → 2

# 全行を list[dict] で取り出す（コピー）
rows = table.read_rows()
```

| やりたいこと | API |
|---|---|
| `n` 行目を 1 件取りたい | `table[n]` |
| 全行を回したい | `for row in table:` |
| 行数 | `len(table)` または `table.count()` |
| `list[dict]` で受け取る | `table.read_rows()` |
| 全行を置き換え | `table.replace(rows)` |
| 1 行 / 複数行を末尾に追加 | `table.append(row)` / `table.append(rows)` |

`Transfer.unmatched()` の `only_in_read` は `Table`（コピー）、
`only_in_write` は **作業 Table の実体行**（`list[Row]`）。`only_in_write` の
行を書き換えると `transfer.result()` に出るので、追加候補を `append()` する前に
加工できる（[README「モジュール一覧」](../README.md#モジュール一覧) 参照）。

---

## 関連

- [README](../README.md) — ライブラリ全体の概要と環境構築
- [公開 API](自動生成/API.md) — 型ヒント付き署名・引数・戻り値・例外
