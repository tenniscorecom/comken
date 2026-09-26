# comken コーディング規約

comken を使って業務自動化スクリプトを書く人と、comken 本体を編集する人の両方向けの規約。

- **1〜14 章**: comken を使うプロジェクトを書く人全員が守る最小限の規約
- **15 章以降**: comken 本体（このリポジトリ）を編集する人だけが追加で守る規約

迷ったら 1〜14 章だけ見ればよい。

---

## 目次

1. [基本方針](#1-基本方針)
2. [命名規則](#2-命名規則)
3. [import の書き方](#3-import-の書き方)
4. [型ヒント](#4-型ヒント)
5. [定数とマジックナンバー](#5-定数とマジックナンバー)
6. [分岐の書き方（if / elif / match）](#6-分岐の書き方if-elif-match)
7. [例外](#7-例外)
8. [ロギング](#8-ロギング)
9. [コメント](#9-コメント)
10. [日時の扱い](#10-日時の扱い)
11. [config.ini の書き方](#11-configini-の書き方)
12. [リソース管理（with 文）](#12-リソース管理with-文)
13. [dataclass・定数クラスの使い分け](#13-dataclass定数クラスの使い分け)
14. [テスト](#14-テスト)
15. [モジュール内の並び順](#15-モジュール内の並び順)
16. [関数の複雑さ](#16-関数の複雑さ)
17. [getter / setter は書かない](#17-getter-setter-は書かない)
18. [デコレーター](#18-デコレーター)
19. [外部依存ライブラリの実装規則（Excel / Windows / ブラウザ）](#19-外部依存ライブラリの実装規則excel-windows-ブラウザ)
20. [命名・型・dataclass・コメント・例外・ロギングの追補](#20-命名型dataclassコメント例外ロギングの追補)
21. [サイト／組織クラスを昇格させる基準](#21-サイト組織クラスを昇格させる基準)
22. [例外クラスを足す基準](#22-例外クラスを足す基準)
23. [品質確認](#23-品質確認)
24. [コードを読む順番](#24-コードを読む順番)

---

## 1. 基本方針

| ルール | 内容 |
|---|---|
| **Ruff** に準拠する | comken と同じ設定（`E`/`F`/`W`/`I`/`B`/`UP`/`SIM`/`PTH`/`C4`/`LOG`/`G`/`T20`/`DTZ`/`RUF`） |
| **型ヒント**を必ず書く | 引数・戻り値の両方 |
| **マジックナンバー禁止** | 数値・文字列定数は名前付き定数にする |
| `print` は禁止 | ログは `logging` を使う |
| コメントは「なぜ」を書く | コードを読めば分かる「何を」は書かない |
| **同じことをする書き方を2つ作らない** | 別名・薄い委譲メソッド・「便利のため」の二重の入口を置かない |

---

## 2. 命名規則

| 種別 | 規則 | 例 |
|---|---|---|
| クラス名 | PascalCase | `Excel`, `LoginPage`, `CsvMerger` |
| 定数・固定値 | UPPER_SNAKE_CASE | `COL_Q`, `SHEET_NAME`, `WAIT_SECONDS` |
| 関数・メソッド | snake_case | `iter_rows()`, `run_macro()` |
| 変数 | snake_case | `csv_lookup`, `matched_rows` |
| モジュール・ファイル名 | snake_case | `handler.py`, `driver_update.py` |
| フォルダ名 | snake_case | `excel/`, `browser/` |
| 内部用（外から呼ばない） | `_` プレフィックス | `_sheet()`, `_click()` |
| config.ini のセクション・キー | UPPER_SNAKE_CASE | `[FILES]`, `OUTPUT_FOLDER` |
| テストクラス | `Test` + PascalCase | `TestExcel`, `TestCSV` |
| テストメソッド | `test_` + snake_case | `test_reads_all_rows` |

### 名前の付け方の原則

| ルール | 良い例 | 悪い例 |
|---|---|---|
| 役割が分かる名前にする | `load_setting` | `load`, `f` |
| 略しすぎない | `sheet_name` | `sn`, `s` |
| bool は is / has / can で始める | `is_empty`, `has_header` | `empty`, `header` |
| 返り値が複数なら複数形 | `rows`, `records` | `row`, `record` |
| 否定形の変数名を使わない | `is_valid = True` | `is_invalid = False` |

`cfg`（config）、`src`（source）、`tmp`（temporary）は広く定着した慣用略語として許容します。
その他の、意味を推測しないと読めない略語は避けてください。

---

## 3. import の書き方

| ルール | 理由 |
|---|---|
| 名前を提供するパッケージまで明示して import する | ファイルの先頭だけで依存範囲が分かる |
| **相対 import を使わない**（`from .X` / `from ..X` は禁止） | 必ず `from comken.X.Y import Z` のようにパッケージルートからの絶対パスで書く |
| ワイルドカード import（`import *`）は禁止 | 使っている名前がどこから来たか追えなくなる |
| 並び順は「標準ライブラリ → サードパーティ → 自分のコード」 | Ruff の `I` が自動で整列する |

```python
# 良い
from comken.toolbox.excel import Excel

# 悪い（ドットを数えないと依存先が分からない）
from ..foo import Bar

# 悪い（使う名前と依存範囲が分からない）
from comken.toolbox.utils import *
```

comken のどの名前を import してよいかは [README「使うときの約束」](../README.md#使うときの約束)を参照してください。

---

## 4. 型ヒント

すべての関数に引数・戻り値の型ヒントを付けます。

```python
# 悪い（型が分からない）
def find_latest(folder, pattern="*.xlsx"):
    ...

# 良い
def find_latest(folder: str | Path, pattern: str = "*.xlsx") -> Path | None:
    ...
```

原則として `Any` は使わず、具体的な型を付けてください。

---

## 5. 定数とマジックナンバー

コードの中に突然出てくる意味不明な数値や文字列を**マジックナンバー**と呼びます。

```python
# 悪い例
rows = com.read_row_values("売上データ", min_row=2)
if file_size > 10485760:
    ...

# 良い例
SHEET_NAME = "売上データ"
HEADER_ROW = 1
LOCAL_COPY_THRESHOLD_MB = 10
LOCAL_COPY_THRESHOLD_BYTES = LOCAL_COPY_THRESHOLD_MB * 1024 * 1024  # 計算式のまま書く

rows = com.read_row_values(SHEET_NAME, min_row=HEADER_ROW + 1)
if file_size > LOCAL_COPY_THRESHOLD_BYTES:
    ...
```

| ルール | 詳細 |
|---|---|
| **大文字スネークケース** | `SHEET_NAME`, `MAX_RETRY_COUNT` |
| **場所** | ファイルの先頭またはクラスの先頭（メソッドより上）にまとめる |
| **計算式はそのまま書く** | `10 * 1024 * 1024`（`10485760` より意味が伝わる） |
| **選択肢を渡す引数は comken の定数クラスを使う** | `save_as(path, file_format=FileFormat.CSV)` のように。Excel COM の保存形式など、列挙に意味があるものは定数クラスで渡す |

---

## 6. 分岐の書き方（if / elif / match）

| 場面 | 使うもの |
|---|---|
| 前提条件・エラー条件を先に弾く | ガード節（`if 異常: raise` / `return` で早期に抜ける） |
| 決まった値の集合から1つを選ぶ（すべて対等な選択肢） | `elif` の連鎖 |
| 型・構造で分岐する（`isinstance` の連鎖になりがちなもの） | `match` / `case` |

```python
# 良い（ガード節で異常系を先に片付ける）
def process(row: dict) -> str:
    if not row:
        raise ValueError("空の行は処理できません")
    if "id" not in row:
        raise KeyError("id 列がありません")
    return row["id"]
```

```python
# 良い（対等な値の分岐は elif）
if status == "Success":
    ...
elif status == "Failed":
    ...
elif status == "Aborted":
    ...
```

分岐が増えすぎたら、`elif` / `match` を無理に `if` の羅列に置き換えず、分岐そのものを関数へ切り出してください。

---

## 7. 例外

**独自のカスタム例外クラスを新しく定義しないでください。** プロジェクト固有の失敗は、
comken が提供する例外（`ComkenError` 系）か、Python の標準例外（`ValueError` / `RuntimeError` 等）を
そのまま使います。

理由: プロジェクトごとに例外階層を作ると、覚えるべき型がプロジェクトの数だけ増え、
他のプロジェクトへ使い回せません。カスタム例外の設計・階層化は comken 本体の役割です。

`FileNotFoundError`（ファイル不在）、`TimeoutError`（待機時間超過）、`ValueError`（標準的な引数の検証）は、
そのまま送出して構いません。ただし `Exception` を直接送出してはいけません。

例外は握りつぶさないでください（`except: pass` は禁止）。失敗を隠すと原因究明ができなくなります。

---

## 8. ロギング

`print` は禁止です。必ず `logging` を使います。

```python
import logging

logger = logging.getLogger(__name__)

logger.info("処理開始: %s", file_path)
logger.debug("詳細: %s", value)
logger.warning("ファイルが見つかりません: %s", path)
logger.error("エラーが発生しました", exc_info=True)  # exc_info=True でスタックトレースも出力
```

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

## 9. コメント

「なぜ」を書きます。コードを読めば分かる「何を」は書きません。

```python
# 良い例（なぜを説明している）
# NAS 上の大きなファイルを直接開くと遅く不安定なため、ローカルにコピーしてから開く
if src.stat().st_size > threshold:
    shutil.copy2(src, tmp_path)

# 悪い例（コードを読めば分かる）
i = i + 1  # i に 1 を加算する
rows = f.to_rows()  # 行を読み込む
```

`# noqa` / `# type: ignore` のような特殊コメントを使うときは、必ず理由もコメントに書いてください。

```python
from module import something  # noqa: F401  # F401 = インポート未使用の警告を無視
```

---

## 10. 日時の扱い

- 現在時刻・今日の日付は共通の `now()` / `today()`（`comken`）を使い、
  `datetime.datetime.now()` / `datetime.date.today()` を直接呼ばないでください。
- CSV・ファイル名・帳票などの業務日付は `datetime.date` のまま扱い、タイムゾーンを付けません。
- 経過時間の計測は `time.perf_counter()` を使います。

---

## 11. config.ini の書き方

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

## 12. リソース管理（with 文）

ファイル・ドライバー・COM オブジェクトは必ず `with` 文で確実に解放します。

```python
# 良い
with Excel("data.xlsx") as f:
    table = f.read("Sheet1")
```

---

## 13. dataclass・定数クラスの使い分け

| やりたいこと | 使うもの | 例 |
|---|---|---|
| 決まった値の一覧を名前で持つ（インスタンスを作らない） | ただのクラス属性（定数クラス） | `Color.RED`, `FileFormat.CSV` |
| 複数の値をひとまとまりで持ち運ぶ「データの箱」 | `@dataclass` | 集計結果・検索結果など |

```python
class Color:
    RED = "FF0000"
    YELLOW = "FFFF00"

cell.fill = Color.RED   # "FF0000" と書くより意味が明確
```

返す値が **2個まで**ならタプルでよく、**3個以上**になったら `@dataclass` を検討してください。

---

## 14. テスト

テストは参考パターンとして。書き方を知っておくと後で助かります。

```python
class TestCSVFindsRow:
    def test_finds_existing_row(self, sample_csv):
        """キーに一致する行を返す。"""
        with CSV(sample_csv) as csv_file:
            rows_by_key = csv_file.read().index("注文番号")
        assert rows_by_key["A001"]["金額"] == "1000"
```

| ルール | 例 |
|---|---|
| テストクラス名は `Test` + 対象クラス名 | `TestExcel`, `TestCSV` |
| テストメソッド名は `test_` + 何を確認するか | `test_returns_none_when_not_found` |
| 一時ファイルは `tmp_path` フィクスチャを使う | `def test_something(tmp_path):` |

---

## 15. モジュール内の並び順

「上から順に読めば、重要なものから細部へ進む」新聞スタイルで統一する。
レビューや読解のとき、ファイルの前半だけで全体像がつかめる。

| 順番 | 置くもの |
|---|---|
| 1 | モジュール docstring（1行目は `パッケージルートからの相対パス.py — 役割`、続けて背景・使い方） |
| 2 | import |
| 3 | `logger`・型変数（`TypeVar` / `ParamSpec`） |
| 4 | 定数・定数クラス |
| 5 | 主役の公開クラス（モジュール名が指すもの） |
| 6 | その他の公開クラス・公開関数、およびそれぞれが使う内部ヘルパー（`_` プレフィックス） |

```python
"""example/handler.py — ○○ユーティリティ"""            # 1. docstring
import logging                          # 2. import

logger = logging.getLogger(__name__)    # 3. logger

DEFAULT_TIMEOUT = 30                    # 4. 定数

class CSV:                              # 5. 主役の公開クラス
    ...

def merge_csv(paths: list) -> Path:     # 6. 公開関数（メイン）
    encoding = _detect_encoding(paths[0])
    ...

def _detect_encoding(path: Path) -> str:  # merge_csv() だけが使うヘルパーなので直後に置く
    ...
```

**内部ヘルパーは「使う公開関数のすぐ下」に置く。** ファイル末尾へまとめて追いやらない。
公開関数が複数あるモジュールでは、**各公開関数 → その関数が使うヘルパー**の
組を、公開関数の重要度順（メインで使う関数を上、そこから呼ばれるものを直後）に並べる。

**複数の公開関数から共通して呼ばれるヘルパーは、最初に使われる箇所より前に
出して独立させる。** 特定の1関数専用のヘルパーと同列に埋もれさせない。

```python
def _shared_helper():  # 複数の公開関数が使うので、呼び出し側より上に出す
    ...

def download_scheduled():         # 公開関数A（メイン）
    _shared_helper()
    ...

def _download():                  # download_scheduled() だけが使うヘルパー
    _shared_helper()
    ...
```

**例外:** クラス属性の初期化（クラス本体）が import 時に呼ぶヘルパーは、
Python の実行順の都合でそのクラスより上に置くしかない。
その場合は `# NOTE:` コメントで「クラス定義時に使うため上に置く」と理由を書く。

---

## 16. 関数の複雑さ

**長さは測らない。分岐の絡み合いを測る。**

単調に並んでいるコードは長くても読める（GUI の組み立て、引数の検証、表示の整形など）。
読めなくなるのは、**1つの関数が同時にいくつものことをやっている**とき——
進捗を追いながら本来の処理を進める、失敗の種類ごとに違う後始末をする、といった形。

**守られ方:** Ruff の `C90`（mccabe）が `max-complexity = 10` で検知する。
**`select` に `C90` を入れただけでは効かない**（`[tool.ruff.lint.mccabe]` の設定が要る）。

閾値の 10 は「いま全部通る一番きつい値」。これ以上ややこしくなった時点で落ちる。
**引っかかったら、まず「この関数はいくつのことをやっているか」を数える。**
たいてい2つ以上あり、分ければ複雑さも一緒に下がる。

---

## 17. getter / setter は書かない

Java 風の `get_x()` / `set_x()` は使わない。
`@property` は原則使わない。ただし**外部から上書きさせたくない属性の読み取り専用公開**には使ってよい。

```python
# 良い（上書きさせたくない属性の公開に @property を使う）
class BrowserSession:
    @property
    def raw(self) -> webdriver.Edge:
        return self._driver  # 外部から raw = xxx と上書きさせない
```

> **Config は継承しない。** `Config.__new__` はパス単位でキャッシュ済みの
> インスタンスを返すため、`AppConfig(path)` を呼んでも素の `Config` が返り、
> サブクラスで足したメソッドは `AttributeError` になる。常に
> `from comken import config` で `config.SECTION.KEY` を直接読む。

`@property` の使い分け:

| 場面 | 方針 |
|---|---|
| 計算値（パス組み立て等） | インラインで書く |
| 複数箇所で使う計算値 | モジュールレベル定数に入れる |
| 呼ぶたびに処理が走ることを明示したい | 普通のメソッド |
| 書き換えてほしくない内部属性の公開 | `@property`（読み取り専用として公開）|

---

## 18. デコレーター

**使わないのが基本方針。** 明確な必要性がない限り使わない。

| デコレーター | 方針 |
|---|---|
| `@staticmethod` | 原則モジュールレベル関数にする。クラスと概念的に切り離せない場合は使ってよい |
| `@classmethod` | ファクトリメソッド（別コンストラクタ）にだけ使う |
| `@cache` / `@lru_cache` | 使わない。状態はインスタンスで持つ |
| カスタムデコレーター | 書かない |

### @classmethod の使いどき

別コンストラクタが必要なときだけ使う。

```python
class Excel:
    @classmethod
    def from_template(cls, template_path: Path, output_path: Path) -> "Excel":
        """テンプレートをコピーして新しい Excel を返す。"""
        shutil.copy2(template_path, output_path)
        return cls(output_path)

# 呼び出し側
f = Excel.from_template(TEMPLATE_PATH, output_path)
```

### @staticmethod の使いどき

`self` も `cls` も使わない場合、**原則はモジュールレベル関数**にする。
ただし、そのクラスと概念的に切り離せないヘルパー（呼び出し元クラス以外からは使わない等）は `@staticmethod` でよい。

```python
# 原則：クラスに属している必要がないならモジュールレベル関数
def normalize_key(key: str) -> str:
    return key.strip().upper()

# 例外：CSV 専用のバリデーションはクラス内に置く
class CSV:
    @staticmethod
    def _validate_columns(rows: list[dict], columns: list[str]) -> None:
        ...  # CSV 以外から呼ばれることを想定していない
```

---

## 19. 外部依存ライブラリの実装規則（Excel / Windows / ブラウザ）

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
（[12. リソース管理（with 文）](#12-リソース管理with-文) 参照）。

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

## 20. 命名・型・dataclass・コメント・例外・ロギングの追補

本体編集で 1〜14 章に追加で必要になる規則。

### 命名

#### 略語の扱い（クラス名・例外名）

PEP 8 は CapWords の中で略語を使う場合、**略語の文字をすべて大文字にする**よう推奨している:

> When using abbreviations in CapWords, capitalize all the letters of the abbreviation.
> Thus `HTTPServerError` is better than `HttpServerError`.

**クラス名・例外名に限り、略語はすべて大文字にする。** 表記の揺れを残さないため、
同じ略語の小文字始まりと全大文字が文書内で混ざらないよう統一する。

| 種別 | 例 | 備考 |
|---|---|---|
| 一般的な略語（クラス名） | `CSVError`, `APIMetrics`, `ExcelCOMHandler`, `SalesforceReportIDNotFoundError`, `HolidayError` | すべて大文字 |
| 複合語の略語（例外名） | `SalesforceReportIDNotFoundError`, `SalesforceReportTruncatedError` | `ID` も2文字だが大文字 |
| 固有名詞・ブランド名 | `OAuth`, `DPAPI`, `HTTP` | 固有名詞としての表記をそのまま使う（例: `RefreshTokenOAuth`） |

snake_case の世界（関数名・変数名・モジュール名・パッケージ名・config キー）は PEP 8
に従い**略語を小文字のまま**にする。`api_key` を `API_KEY` にしない、`api_usage` を
`APIUsage` にしない。

#### 公開メソッドの動詞

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
| 差分を求める | `diff_` | `diff_row()`, `diff_rows()` |
| 書き込む・保存する | `write_` / `save_` | `write_rows()`, `save_draft()` |
| 末尾へ追加する | `append_` | `append_rows()` |
| 生のスクリプトを実行する | `execute_` | `execute_script()` |

HTTP の `get()`、キー・値ストアの `get()` / `set()` のように、その操作の意味が
上の動詞表のどれとも一致しないときだけ例外として認める。**「分野で確立している
から」「一般的によく使われるから」だけを理由にした例外は許さない**。

#### 読み取り系メソッドの動詞

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

### 型ヒント

#### `Any` の許容範囲

原則として `Any` は使わず、具体的な型を付ける。
ただし、COM オブジェクト、Excel セル値、型情報を提供しない外部ライブラリとの境界など、
正確な型を現実的に表せない動的境界では `Any` を最小限の範囲に限って許容する。
`Any` を通常のアプリケーションロジックへ伝播させず、境界の内側で具体型へ変換する。

#### `from __future__ import annotations`

`from __future__ import annotations` は全ファイルには入れず、前方参照、循環 import の回避、
`TYPE_CHECKING` 内だけで import する名前を型注釈に使う場合など、注釈の遅延評価が必要な
ファイルにだけ入れる。残す場合は、必要な理由を import の直前にコメントで書く。

**型注釈のクラス名を `"Table"` のようにダブルクォーテーションで囲まない。** 前方参照や
`TYPE_CHECKING` 内だけの import は、上の `from __future__ import annotations` で解決する。

### dataclass・定数クラス・Enum

#### frozen の使い分け

`@dataclass(frozen=True)` にすると、**作った後にフィールドを書き換えられなくなる**（読み取り専用）。
うっかり値を上書きする事故を防げるので、**「一度作ったら変わらない値のセット」には frozen を付けるのが安全**。

| 効果 | 意味 |
|---|---|
| 書き換え禁止 | 「途中で誰かが値を変えたせいでおかしくなった」を防げる |
| ハッシュ可能になる | `set` に入れたり `dict` のキーにできる（変わらない値だから安全にできる） |

使い分けの目安:

- **計算結果・設定値・マスタなど「確定したら変えない」もの** → `frozen=True`（推奨）
- **作った後に組み立てながら値を詰めていくもの**（ループで `obj.count += 1` する等）→ frozen なし

> 注意: frozen はトップレベルの再代入（`fee.rate = ...`）を止めるだけ。
> 中にリストを持たせた場合、そのリストの中身（`fee.items.append(...)`）までは止められない。
> 変えたくないなら中身も `tuple` にする。

#### Enum を使う/使わない理由

`enum.Enum` を使う手もあるが、値を取り出すのに `Color.RED.value` と `.value` が要るなど
初学者に一手間多い。**この規約ではプレーンなクラス属性を使う**（typo が即エラーになる Enum の利点は
クラス属性でも同じ）。

### コメント

#### 特殊コメント（ツール向け）

ツールが解釈する「魔法のコメント」。コードの動作ではなくツールの挙動を制御する。

| コメント | 用途 |
|---|---|
| `# noqa` | リント警告を抑制する（Ruff / flake8） |
| `# type: ignore` | 型チェックエラーを抑制する（mypy / pyright） |
| `# fmt: off` / `# fmt: on` | フォーマッターを一時的に無効化する |
| `# pragma: no cover` | カバレッジ計測から除外する（pytest-cov） |

使い方の原則:

| ルール | 理由 |
|---|---|
| 必ず理由もコメントに書く | 「なぜ抑制しているか」が後で分からなくなる |
| `# noqa`（エラーコードなし）は乱用しない | 本物のバグも一緒に隠してしまう |
| できるだけ根本原因を修正する | 特殊コメントは最終手段 |

### 例外

#### try / except での受け取り方

捕捉する粒度は、対応の細かさに合わせて3段階から選ぶ。細かい方から順に `except` を並べる
（先に基底を書くと、下位の例外がそこで捕まって個別の対応に届かない）。

| except の粒度 | 使いどころ |
|---|---|
| 個別の例外 | そのエラーだけ個別に対応したいとき |
| カテゴリの基底 | ある分野のエラーをまとめて処理したいとき |
| ライブラリの基底 | ライブラリ由来のエラーを全部キャッチしたいとき |

### ロギング

#### メッセージは `%s` プレースホルダで渡す（f-string にしない）

```python
# 悪い（呼び出し元のログレベルに関わらず、毎回文字列を組み立ててしまう）
logger.debug(f"詳細: {expensive_repr(value)}")

# 良い（ログレベルで出力しないと決まっていれば、フォーマット自体が走らない）
logger.debug("詳細: %s", expensive_repr(value))
```

`logging` は「そのレベルを実際に出力する」と決まってから初めて `%s` を埋める
（遅延評価）。f-string や `str.format()` は呼び出した時点で必ず文字列を組み立てて
しまうため、`logger.debug(...)` が実際には捨てられる本番環境でも計算コストを払う。

#### ログレベルの選び方

| レベル | 使いどころ |
|---|---|
| `DEBUG` | 開発中の詳細な経過（変数の中身、分岐の通過箇所）。本番では出力しない前提 |
| `INFO` | 正常系の節目（処理の開始・完了、何件処理したか）。運用担当者が後から追う想定 |
| `WARNING` | 処理は継続するが、気づいてほしい異常（想定外だが致命的ではない値、フォールバック動作） |
| `ERROR` | 処理が失敗して中断・スキップした。例外をそのまま送出する箇所では省略してよい（呼び出し元がログに残せる） |

---

## 21. サイト／組織クラスを昇格させる基準

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
  こう運用する」）を抱え込む場合**。`salesforce_downloader` が代表例（管理表の
  スキーマ・履歴 CSV の形式・スケジュール判定を抱えていたため、別リポジトリへ
  切り出した）。
- 切り出したものは `pip install` 可能な独立パッケージ（`comken_xxx` のように
  アンダースコア区切りで import）として配布し、comken 自体は依存を増やさない。

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

**独立リポジトリへ分離する手順**:

1. 切り出すディレクトリ（例: `comken/services/salesforce_downloader/`）と
   関連例外（例: `comken/exceptions/downloader.py`）のファイルを、
   新リポジトリへ移動する
2. 新リポジトリの `pyproject.toml` でパッケージ名（例: `comken_salesforce_downloader`）を
   決め、`pip install` 可能な形に整える
3. comken 側の import 元を新パッケージへ切り替え、利用プロジェクトの
   import 文を更新する
4. comken 側からは旧ディレクトリと旧例外を削除する

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

## 22. 例外クラスを足す基準

例外の書き方（メッセージに対処を入れる、素の `Exception` を投げない等）は
[7. 例外](#7-例外) に従う。階層の全体像は
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

## 23. 品質確認

変更時はRuff、フォーマット、pytest、Markdownリンク検査を実行する。実行件数や監査日を
文書へ転記するとすぐ古くなるため、結果はCIとGit履歴を正本にする。

次の境界はモックだけでは保証できない。関連機能を変更したリリースでは実機で確認する。

- Excel / Access / OutlookのCOM差異、Officeの版差、権限、ファイルロック
- SeleniumとEdgeDriverの版差、ポップアップ、証明書、ダウンロード完了判定
- Salesforce組織ごとの権限、ECAのレスポンス項目、API制限
- DPAPIのWindowsユーザー・PC間の非互換性

---

## 24. コードを読む順番

本体をレビュー・読解するときの参照地図。

### 読む順番（おすすめ）

1. **この規約（1〜23 章）** — 全ファイル共通のルール。これを先に読むと以降が速い
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

全モジュールが同じ並び順で書かれている（詳細: [15. モジュール内の並び順](#15-モジュール内の並び順)）:

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

- [README](../README.md) — comken 全体の使い方
- [公開 API](自動生成/API.md) — 型ヒント付き署名・引数・戻り値・例外
- [設計書](ARCHITECTURE.md) — 現在の設計
- [設計判断の履歴](HISTORY.md) — 理由・却下した案
