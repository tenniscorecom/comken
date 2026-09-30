# comken コーディング規約

comken を使って業務自動化スクリプトを書く人と、comken 本体を編集する人の両方向けの、**comken 固有の**規約。
言語に関係ないルールは [CONVENTIONS_COMMON.md](CONVENTIONS_COMMON.md)、Python の言語としてのルールは
[CONVENTIONS_PYTHON.md](CONVENTIONS_PYTHON.md)、VBA は [CONVENTIONS_VBA.md](CONVENTIONS_VBA.md) にある。
この文書はそれらを読んだ前提で書き、同じことを繰り返さない。

| 読む人 | 読むもの |
|---|---|
| comken を使うプロジェクトを書く人 | 共通 → Python 1〜14 章 → この文書の 1〜7 章 |
| comken 本体を編集する人 | 上に加えて、Python 15 章以降 → この文書の 8 章以降 |
| VBA を書く人 | 共通 → VBA |

---

## 目次

1. [import してよい名前](#1-import-してよい名前)
2. [例外](#2-例外)
3. [ロギング](#3-ロギング)
4. [日時](#4-日時)
5. [config.ini の書き方](#5-configini-の書き方)
6. [選択肢を渡す引数](#6-選択肢を渡す引数)
7. [リソース管理（with 文）](#7-リソース管理with-文)
8. [外部依存ライブラリの実装規則（Excel / Windows / ブラウザ）](#8-外部依存ライブラリの実装規則excel-windows-ブラウザ)
9. [公開メソッドの動詞](#9-公開メソッドの動詞)
10. [サイト／組織クラスを昇格させる基準](#10-サイト組織クラスを昇格させる基準)
11. [例外クラスを足す基準](#11-例外クラスを足す基準)
12. [品質確認](#12-品質確認)
13. [コードを読む順番](#13-コードを読む順番)

---

## 1. import してよい名前

comken のどの名前を import してよいかは [README「使うときの約束」](../README.md#使うときの約束)を参照してください。
import の書き方そのもの（相対 import 禁止など）は [Python 3 章](CONVENTIONS_PYTHON.md#3-import-の書き方)。
comken 本体では相対 import を Ruff（`TID`、`ban-relative-imports = "all"`）が止める。

---

## 2. 例外

**独自のカスタム例外クラスを新しく定義しないでください。** プロジェクト固有の失敗は、
comken が提供する例外（`ComkenError` 系）か、Python の標準例外（`ValueError` / `RuntimeError` 等）を
そのまま使います。

理由: プロジェクトごとに例外階層を作ると、覚えるべき型がプロジェクトの数だけ増え、
他のプロジェクトへ使い回せません。カスタム例外の設計・階層化は comken 本体の役割です。

例外の書き方そのもの（握りつぶさない・`Exception` を直接送出しない）は [Python 7 章](CONVENTIONS_PYTHON.md#7-例外)。

**例外: 他の処理の土台になる基幹プロジェクト**（例: `Salesforceレポートダウンローダー`）
**は、自分の例外クラスを持ってよい。** その場合も comken の例外（`ComkenError`
やカテゴリ例外）を継承し、個別のクラスは呼び出し側が型で処理を変えるものだけにする
（11 章と同じ基準）。

---

## 3. ロギング

ロガーの作り方・`%s` で渡すこと・レベルの選び方は [Python 8 章](CONVENTIONS_PYTHON.md#8-ロギング)。
実行するときのログ設定の呼び出し方は [core「Logger」](機能/core.md#logger)を参照してください。

### ブラウザのページオブジェクトに書くとき

自分のサイト用に作るページオブジェクト（`LoginPage` 等）では、`click()` / `input()` /
`has_element()` / `read_text()` といった comken の操作は**呼ぶだけで自動的にログが残る**
（comken 側の実装が既に `logger.debug` を出している）。そのため、操作1つ1つに自分で
ログを書き足す必要はありません。

自分でログを足すのは、汎用ログだけでは残らない**分岐の理由**があるときだけにしてください。

その際は `logger.info` を使ってください。**既定のログレベルは INFO で、DEBUG は
出ません**（[core「Logger」](機能/core.md#logger) の `setup_logging()` /
`setup_local_logging()` とも、既定のコンソール・ファイル出力は INFO 以上）。
comken 側の操作ログが `logger.debug` なのは、1操作ごとに出ると量が多すぎるため
既定で抑制しているからで、ページオブジェクト側で足す「分岐の理由」は逆に、
後から実行ログを見て気付けないと意味が無いので info にします。

```python
# 良い例（要素が無いという分岐の理由は click_if_present() 自身が info で
# 残すので、呼び出し側で同じ事実を重ねてログしなくてよい）
self.click_if_present(self.LOGIN_BTN)

# 良い例（comken 側のログでは分からない、サイト固有の意味を持つ分岐だけ
# 呼び出し側で info を足す）
if ChangePasswordPage.PATH in current_url:
    logger.info("パスワード変更画面へ遷移しました: current_url=%s", current_url)
    self.to(ChangePasswordPage)

# 悪い例（comken 側が既に出しているログの重複）
logger.debug("ログインボタンをクリックします")
self.click(self.LOGIN_BTN)
```

「ボタンがあればクリック、無ければ何もしない」（`click_if_present`）や
「エラー要素があれば、その文言で例外を送出する」（`raise_if_shown`）は
サイトが変わっても同じ形になりがちなパターンです。ページオブジェクトへ
`has_element()` + `click()` / `raise SomeError(...)` を自分で書く前に、
comken の `Page` が既に持っている汎用メソッドで済まないか確認してください。

具体例は [browser.md「ログイン失敗まわり」](機能/browser.md#ログイン失敗まわり期限切れ認証エラー非同期の揺れ)を参照してください。

---

## 4. 日時

- 現在時刻・今日の日付は共通の `now()` / `today()`（`comken`）を使い、
  `datetime.datetime.now()` / `datetime.date.today()` を直接呼ばないでください。
- 業務日付・経過時間の扱いは [Python 10 章](CONVENTIONS_PYTHON.md#10-日時の扱い)。

---

## 5. config.ini の書き方

セクション名は決まった並びから選びます。プロジェクトごとに違う名前を作らないでください。

| セクション | 中身 | いつ書くか |
|---|---|---|
| `[FILES]` | 入力元・出力先のパス。**フォルダもファイルもここ** | 常に |
| `[CSV]` | CSV の読み書き設定（文字コード・日付書式など） | 使うときだけ |
| `[EXCEL]` | Excel の読み書き設定（シート名・見出し行など） | 使うときだけ |
| `[BROWSER]` | ブラウザの設定（`HEADLESS` など） | 使うときだけ |
| `[CREDENTIALS]` | 認証情報のシステム名（値そのものは DPAPI） | 使うときだけ |
| `[〇〇_MAPPING]` | 列の対応表。ここだけ**キーを実物どおり**に書く | 使うときだけ |

**config.ini に書くものの基準**: 「環境によって変わる値」というより、
**非エンジニアが触るもの・毎日/毎週/毎月のように頻繁に変わっていくもの**を config.ini へ出す、
という考え方で選んでください。エンジニアでない人が変更しやすくすることが目的です。

```ini
[FILES]
; フォルダは INPUT_FOLDER 1個だけ（滅多に変わらない）。ファイル名は
; INPUT_〇〇 で1行1ファイルに分ける（毎日・毎月ここだけ書き換える運用に強い）
INPUT_FOLDER = ./input
INPUT_受注_EXCEL = 受注一覧.xlsx
OUTPUT_FOLDER = ./output
```

パスは **config.ini からの相対パス** で書くのが既定です。区切り文字を含まない値
（`INPUT_FOLDER = input`）は `Path` にならず文字列のままになるため、
相対パスとして扱わせたいときは `./input` のように `./` を付けてください。

---

> **Config は継承しない。** `Config.__new__` はパス単位でキャッシュ済みの
> インスタンスを返すため、`AppConfig(path)` を呼んでも素の `Config` が返り、
> サブクラスで足したメソッドは `AttributeError` になる。常に
> `from comken import config` で `config.SECTION.KEY` を直接読む。

---

## 6. 選択肢を渡す引数

Excel COM の保存形式など、列挙に意味がある選択肢は、生の文字列ではなく comken の定数クラスで渡す。

```python skip
save_as(path, file_format=FileFormat.CSV)
```

定数クラスそのものの考え方は [Python 12 章](CONVENTIONS_PYTHON.md#12-dataclass定数クラスの使い分け)。

---

## 7. リソース管理（with 文）

comken のクラス（`Excel` / `CSV` / `BrowserSession` など）は `with` 文で開きます。

```python
# 良い
with Excel("data.xlsx") as f:
    table = f.read("Sheet1")
```

`with` が使えない COM オブジェクトの解放は [Python 11 章](CONVENTIONS_PYTHON.md#11-リソース管理with-文)。

---

## 8. 外部依存ライブラリの実装規則（Excel / Windows / ブラウザ）

### Excel（openpyxl）

Excel の読み書きは `Excel` を使う。openpyxl を直接触るのはライブラリにない機能が
必要なときだけ。シートに対する書き込み・書式・構造化テーブル操作は `f.sheet(name)` で
取得した `Sheet` に集約し、`Excel` にはブック単位の操作だけを置く。

**書式設定は処理ロジックと分離する**

```python
def apply_header_style(cell) -> None:
    cell.font = Font(bold=True, color="FFFFFF")
    cell.fill = PatternFill(fill_type="solid", fgColor="4472C4")
    cell.alignment = Alignment(horizontal="center", vertical="center")
```

**禁止事項**

| 禁止 | 理由 |
|---|---|
| `data_only=False` のまま数式セルを上書き | 数式が消える |
| 巨大ファイルをそのまま `load_workbook` | メモリ不足。`read_only=True` を使う |

### Windows 操作（pywin32）

pywin32 は **Windows 固有の API** に限定して使う。
ファイル操作は標準ライブラリの `shutil` / `pathlib` を優先する。

| 用途 | 推奨 |
|---|---|
| ファイルコピー・移動・削除 | `shutil`, `pathlib`（標準） |
| VBA マクロの実行 | `pywin32`（COM 経由） |
| ウィンドウ操作 | `pywin32`（win32gui） |
| レジストリ操作 | `pywin32`（win32api） |

COM オブジェクトは `with` 文が使えないため、`try/finally` で確実に解放する
（[Python 11 章「リソース管理（with 文）」](CONVENTIONS_PYTHON.md#11-リソース管理with-文) 参照）。

```python
import pywintypes

try:
    pass  # win32 処理
except pywintypes.error as e:
    logger.error("Win32 API エラー: code=%d, msg=%s", e.winerror, e.strerror)
    raise
```

### ブラウザ自動化（Selenium）

**スクリーンショットは自動キャプチャに任せる**

`BrowserSession` の `with` ブロック内で例外が発生すると、その時点の画面が
`logs/error_セッション名_YYYYMMDD_HHMMSS.png` に**自動保存**される
（[docs/機能/browser.md](機能/browser.md) の「BrowserSession」参照）。

```python
# 良い（何もしない。失敗時の画面は自動で logs/error_*.png に残る）
session.open(url)
session.click(locator)
```

`save_screenshot()` を明示的に呼ぶのは、**例外にならない「見た目のズレ」を残したいとき**
（想定した要素が表示されているかの目視確認、途中経過の記録など）に限る。

```python
# 良い（例外にならないので自動キャプチャの対象外。明示的に撮る必要がある）
session.open(url)
if not session.find_element(confirmation_banner):
    logger.warning("確認バナーが出ていません")
    session.save_screenshot(directory="errors")
```

**保存先はデフォルト（`logs/`）に任せる**

保存先を毎回組み立てない。ファイル名だけ・サブディレクトリだけを指定し、
`logs/` からの相対パスにする。

```python
# 悪い（logs/ の場所を決め打ちしている。環境が変わると壊れる）
session.save_screenshot(Path("logs") / "errors" / f"{name}.png")

# 良い（directory 引数に任せる）
session.save_screenshot(f"{name}.png", directory="errors")
```

---

## 9. 公開メソッドの動詞

### 同じ操作には同じ動詞

同じ操作には同じ動詞を使う。名詞だけのメソッドや、`js()` のように処理が分からない略称は
公開 API に使わない。

| 操作 | 動詞 | 例 |
|---|---|---|
| 処理・マクロ・クエリを実行する | `run_` | `run_macro()`, `run_query()` |
| データや値を読み取る | `read_` | `read_row_values()`, `read_text()`, `read_messages()` |
| 1件を検索する | `find_` | `find_element()` |
| 複数件を絞り込む | `filter_` | `filter_rows()` |
| 存在・状態を判定する | `is_` / `has_` / `can_` | `is_empty()`, `has_element()` |
| 件数を数える | `count_` | `count_elements()` |
| 差分を求める | `diff_` | `diff_row()`, `Table.diff()`, `Table.changes()` |
| 書き込む・保存する | `write_` / `save_` | `write_rows()`, `save_draft()` |
| 末尾へ追加する | `append_` | `append_rows()` |
| 生のスクリプトを実行する | `execute_` | `execute_script()` |

HTTP の `get()`、キー・値ストアの `get()` / `set()` のように、その操作の意味が
上の動詞表のどれとも一致しないときだけ例外として認める。**「分野で確立している
から」「一般的によく使われるから」だけを理由にした例外は許さない**。

### 読み取り系メソッドの動詞

読み取り API は**戻り値の形で名前を分ける**。**戻り値の型と名前を一致させる**のが原則。

| 動作 | 名前 |
|---|---|
| 表として読む | `read() -> Table` |
| 大量データを逐次読む | `iter_rows()` |
| Table を list 化 | `to_rows()` |
| 単一レコード取得 | `get() -> dict` |
| SOQL | `query()` |
| Excel・CSV・Windows のセル/属性を読む | `read_*()` |
| 真偽判定 | `is_*()` / `has_*()` |

**例外: ブラウザ自動化（Page Object Model）は `get_*` のままにする**
（`get_heading()` / `get_error_message()` 等）。Selenium/Playwright を含む
業界慣習が `get_text()` / `get_attribute()` のように `get_*` を標準にしており、
上の「読み取り系は `read_*`」ルールをここへ機械的に当てはめると、ブラウザ
自動化のコードを書く人の直感と衝突する。

**`Salesforce Report API` の `get()` も同様に例外。** `sf.report.get()` は
複数行を返すが、`run()` ではなく `get()` のままにする（呼び出し形として
`sf.report.get()` の方が自然という判断）。

**`Salesforce Report API` の `describe()` 系も動詞表の例外。**
`sf.report.describe()` / `describe_fields()` / `describe_fields_csv()` は
レポートを実行せず定義（列・フィルタ・形式）だけを取得する。Salesforce REST API 自身が
`sobjects/describe` のように「describe」をメタデータ取得の動詞として定義しており、
`read_` へ統一すると Salesforce のドキュメント・エラーメッセージとの対応が取りにくく
なる（ドメインで確立した語を優先する）。

---

## 10. サイト／組織クラスを昇格させる基準

`SiteBase`（ブラウザ）と `SalesforceBase`（組織）は継承して使う前提のクラス。
ライブラリ管理者は「誰かが継承してサイト／組織クラスを作った」という事実を
**ドキュメントの努力目標ではなく起動時の検査**で把握する。サブクラスには
`OWNER = "プロジェクト名 / 担当者"` を必ず書いてもらい、
`comken.toolbox.browser.sites` / `comken.toolbox.salesforce.sites` 配下の
クラス（管理者が昇格を判断したもの）は検査を免除する代わりに `OWNER = "comken"` を書く。

### まず `sites/` か別リポジトリかを決める

社内システムを足すとき、置き場所は**2つある**。どちらか片方とは限らず、両方になることもある。

| 足すもの | 置き場所 | 見分け方 |
|---|---|---|
| **そのシステムへの入り方**（URL・ログイン・行ける画面） | `toolbox/browser/sites/`<br>`toolbox/salesforce/sites/` | **「〜を操作する」で説明できる** |
| **そのシステムを使った社内の手順**（管理表の決まり・保存先の規約・管理番号） | **独立リポジトリ**（`comken-xxx` として分離） | **社内の決まりを知らないと説明できない、かつ 1プロジェクトだけで消費しきれない規模** |

勤怠システムを例にすると:

- 「勤怠サイトを開いて打刻画面へ行く」→ **`sites/`**。サイトの形が分かれば誰でも書ける
- 「毎月末に管理表の全員分を締めて、決まった場所へ決まった名前で出す」→ **別リポジトリ**。
  社内の決まりを知らないと書けず、共通で使い回せる規模なら独立パッケージとして分離する

**サイトクラスは別リポジトリに置かない。** 画面の操作そのものは社内の決まりではなく、
「そのサイトがどうできているか」だから。逆に、管理表や保存先の規約が絡んだ時点で
**独立パッケージ（`comken-xxx`）へ切り出す**ほうが、comken 本体の汎用性を保てる。

**どちらも、まずはプロジェクト側に置く。** 下の原則は両方に当てはまる。

### 原則: 最初は必ずプロジェクト側に置く

新しい社内システムの自動化を作るときは、**必ずプロジェクト側（`src/sites/` や
そのプロジェクト独自の置き場所）に置く**。最初からライブラリへ入れる判断はしない。

後からライブラリへ昇格するのは非破壊的だが、最初にライブラリに入れてしまうと
「外で使うには comken 経由でしか書き始められない」状態になり、外せなくなる。

### ライブラリへ昇格する判断基準

次のいずれかに当てはまったら、ライブラリへ移すことを検討する。

- **2つ目のプロジェクトが同じシステムを触り始めた時点**（重複が実測で出たとき）
- **全社共通の業務システムで、複数プロジェクトから触るのが確実なとき**
- **認証情報（DPAPI のキー名）を伴い、登録名を統一したいとき**
  （例: `kintai_client_id` を複数プロジェクトで同じキーで登録したい）

逆に、**1つのプロジェクトしか触らないうちはプロジェクト側に置く**。
次のようなケースもプロジェクト側に置いてよい。

- 画面が頻繁に変わる、または試験的な自動化のとき
- そのプロジェクト固有の手順（社内申請のフォーマット等）を含むとき

**独立リポジトリへ分離する判断基準**:

- 上記の「ライブラリへ昇格する」基準を満たし、かつ
- **管理表・履歴・スケジュール判定など、社内の運用ルール（≒「このプロジェクトでは
  こう運用する」）を抱え込む場合**。`salesforce_downloader` が代表例（取得を実行する
  部分（管理表・スケジュール・SOQL レポート・取得実行）は `Salesforceレポートダウンローダー`
  プロジェクトへ切り出し、comken 側は履歴の形式と「管理番号で取得済みレポートを
  引く読み取り関数」だけを残した。境界を履歴にしたので、管理表を変えても他の
  プロジェクトは変えなくてよい）。
- 切り出したものは comken を import する独立したプロジェクトとして置き、comken 側からは
  import しない。`pip install` で配るパッケージにはしない（利用側ごとに `pip install` が
  要るのが不便で、一度やめた。HISTORY 6 章「サービス層の分離と再統合」）。

### 昇格の手順

1. プロジェクト側の `src/sites/<システム>.py` を、ライブラリ側の
   `comken/toolbox/browser/sites/<システム>.py`（Salesforce の場合は
   `comken/toolbox/salesforce/sites/<システム>.py`）へ移す
2. クラス内の `OWNER` を `"comken"` に変える（管理者が昇格した印）
3. **`SITES` への登録は不要** — `comken/core/discovery.py` の `find_subclasses()` が
   配下のファイルを自動走査して拾う。**`NAME`（Salesforce の組織クラスは
   `DOMAIN_URL`）を空のままにしない**こと。空だと土台クラス扱いで除外される。
   ファイル・フォルダ名が `_` で始まるものも除外される（雛形置き場）
4. 利用側の import を `from comken.toolbox.browser.sites import <クラス名>` へ書き換える

**移すかどうかはライブラリ管理者が判断する。** プロジェクト側は勝手に
`comken` 配下へファイルを置かず、必ず管理者へ連絡する。

### 衝突防止

ライブラリへ昇格したあと、プロジェクト側で同じ `NAME` のクラスを定義すると、
**起動時に `BrowserError`** で止まる。「すでにライブラリにあるものを
自作している」状態を自動で捕まえるのが目的。

### 管理者が扱うのは、連絡が来たものだけ

**無断で継承されたクラスを探しにいく仕組みは作らない。** `OWNER` を必須にしても、
適当な値を書けば起動できるので、連絡なしの継承は止められない。**止められないものを
検知する道具（走査ツール・利用履歴・事前登録）を常設すると、その道具を保守する仕事だけが残る**
——走らせなければ腐り、書き込み先の権限を管理し続けることになる。

ライブラリ管理者が扱うのは**連絡が来たものだけ**とする。連絡なしに作られたサイト／組織
クラスは、そのプロジェクトの持ち物として扱う。**重複しても壊れるのは共有サーバーの
ライブラリではなく、連絡しなかった側のプロジェクト**（同じシステムのクラスが2つあると、
片方の修正がもう片方に伝わらない）。

一覧が要るようになったら、そのとき `OWNER` を grep すればよい。**`OWNER` を必須に
してあるのは、そのための痕跡を残すためで、監視のためではない。** 起動時に止めるのは、
継承する人に「これは誰の持ち物か」「ライブラリに入れるべきか」を一度考えてもらう関所として。

---

## 11. 例外クラスを足す基準

例外の書き方（メッセージに対処を入れる、素の `Exception` を投げない等）は
[2. 例外](#2-例外) に従う。階層の全体像は
[`ARCHITECTURE.md`「5. 例外体系」](ARCHITECTURE.md#5-例外体系) が正本（ここに図を再掲しない）。

**個別の例外クラスを作るのは、呼び出し側が型によって処理を変える必要がある場合だけ。**
たとえば `except SheetNotFoundError:` で「シートが無ければ空として続ける」ような場合。
それ以外は、カテゴリ例外（`ExcelError` など）にメッセージをつけて送出する。

```python
raise ExcelError(f"シート「{name}」が見つかりません。存在するシート: {sheets}")
```

- 対処が同じ失敗は、カテゴリ例外にまとめ、違いはメッセージで伝える。メッセージには「何が・どこで・どうすればよいか」を入れる
- `ComkenError` の直下に新しいカテゴリを増やさない。`ExcelError` / `CSVError` / `SalesforceError` 等の既存カテゴリに置く
- **統合・削除の前に、利用側プロジェクトを grep する。** 送出・捕捉・型による分岐・クラス名の記録に使われていないかを確かめる
  （comken 内で送出されていないだけでは「未使用」と判断しない。利用者プロジェクトが送出する想定の例外がある）
- 統合したら旧名は残さず削除する（別名も警告も付けない）。旧名を使っていたコードは `ImportError` になる

---

## 12. 品質確認

変更時はRuff、フォーマット、pytest、Markdownリンク検査を実行する。実行件数や監査日を
文書へ転記するとすぐ古くなるため、結果はCIとGit履歴を正本にする。

次の境界はモックだけでは保証できない。関連機能を変更したリリースでは実機で確認する。

- Excel / Access / OutlookのCOM差異、Officeの版差、権限、ファイルロック
- SeleniumとEdgeDriverの版差、ポップアップ、証明書、ダウンロード完了判定
- Salesforce組織ごとの権限、ECAのレスポンス項目、API制限
- DPAPIのWindowsユーザー・PC間の非互換性

---

## 13. コードを読む順番

本体をレビュー・読解するときの参照地図。

### 読む順番（おすすめ）

1. **規約（共通・Python・この文書）** — 全ファイル共通のルール。これを先に読むと以降が速い
2. **`exceptions/`** — カテゴリ別ファイルと個別例外。エラーメッセージの方針
   （業務側の非エンジニアが読んで対処できる文面）もここで分かる
3. **`exceptions/` → `core/dates.py` → `core/files/`** — 依存の少ない基盤
4. **`runtime.py` → `core/config/`** — 実行モードと設定。
   `core/config/__init__.py` は config.ini の初回読み込み完了時に、障害調査用の
   comken バージョンを INFO ログへ1回だけ記録する
5. **`toolbox/csv/file.py` →
   `toolbox/excel/workbook.py` → `toolbox/excel/sheet.py` →
   `toolbox/excel/table.py`** — 一番よく使われる部分。
   ここで「docstring の書き方」「定数クラス」「with 文」のパターンをつかむ
6. **`toolbox/windows/handler.py`** — OS 依存の処理
7. **`toolbox/browser/`** — 外部アプリ（Edge）依存。まず
   [設計書「8. ブラウザ内部設計」](ARCHITECTURE.md#8-ブラウザ内部設計) の全体図を読み、
   `sitebase.py`（`SiteBase` の定義。サイトを書く人が最初に読むファイル）→
   `options.py`（`BrowserOptions` の既定値一覧）→
   `sites/`（`SITES` の置き場。ライブラリ公認サイトの集まり）→
   `management/sessions.py`（1サイト分の WebDriver）
   → `page/`（画面操作。`Page` 本体は `model.py`）の順に読む

### どのファイルも同じ形

全モジュールが同じ並び順で書かれている（詳細: [Python 15 章「モジュール内の並び順」](CONVENTIONS_PYTHON.md#15-モジュール内の並び順)）:

```
1. モジュール docstring   ← そのファイルの役割と使い方（コピペで動く例）
2. import
3. logger・型変数
4. 定数・定数クラス
5. 主役の公開クラス       ← モジュール名が指すもの
6. その他の公開クラス・公開関数
7. 内部ヘルパー（_ 付き）  ← 必ず最後
```

つまり**ファイル先頭の docstring と主役クラスの docstring だけ読めば、そのモジュールの
全体像と使い方が分かる**。細部（内部ヘルパー）は必要なときだけ下へ読み進めればよい。

---

## サンプルコード

具体的な使い方は、規約に書き写すのではなく実際のサンプルコードを参照してください。
更新されるたびに規約とサンプルがズレるのを防ぐためです。

| やりたいこと | サンプル |
|---|---|
| CSV を読み書きする | [examples/csv_read.py](../examples/csv_read.py), [examples/csv_write.py](../examples/csv_write.py) |
| Excel を読み書きする | [examples/excel_read.py](../examples/excel_read.py), [examples/excel_write.py](../examples/excel_write.py) |
| CSV/Excel 間で列を転記する | [examples/column_mapping.py](../examples/column_mapping.py) |
| Table / Transfer の詳しい使い方 | [examples/advanced/table_transfer_design/run.py](../examples/advanced/table_transfer_design/run.py) |
| config.ini を使う | [examples/constants.py](../examples/constants.py) |
| ログを設定する | [examples/logger.py](../examples/logger.py) |
| dry-run・debug モード | [examples/runtime.py](../examples/runtime.py) |
| 例外の使い方 | [examples/exceptions.py](../examples/exceptions.py) |

すべてのサンプルは [examples/README.md](../examples/README.md) にも一覧があります。

---

## 関連

- [共通規約](CONVENTIONS_COMMON.md) / [Python 規約](CONVENTIONS_PYTHON.md) / [VBA 規約](CONVENTIONS_VBA.md)
- [README](../README.md) — comken 全体の使い方
- [公開 API](自動生成/API.md) — 型ヒント付き署名・引数・戻り値・例外
- [設計書](ARCHITECTURE.md) — 現在の設計
- [設計判断の履歴](HISTORY.md) — 理由・却下した案
