# Python コーディング規約（共通）

comken 本体と、comken を使うプロジェクトの**両方に共通する Python の書き方**を定める。
**PEP 8**（Python 公式スタイルガイド）に準拠し、矛盾する場合は本規約を優先する。

**本書には comken 固有のルールを書かない。** どの名前を import してよいか、どの基底例外を
継承するかといった comken に依存する話は他が持つ。本書は comken を知らなくても
読める言語レベルのルールだけを扱い、置き場所が1つに定まるようにする。

| 規約 | 対象 | 内容 |
|---|---|---|
| **本書（CONVENTIONS.md）** | すべての Python コード | 命名・型・定数・例外・ロギング・コメント・テスト等の言語レベルの共通ルール |
| [docs/開発/ライブラリ開発規約.md](ライブラリ開発規約.md) | **comken 本体**を編集する人 | 公開 API（`__all__`）・カスタム例外の階層設計・互換シム・パッケージ構成 |

comken を**使う側**のプロジェクトには規約を置かない。構成は `templates/新規プロジェクト/` の
雛形が、使い方は [README](../../README.md) と `` の各モジュール文書が持つ。

---

## 目次

1. 基本方針
2. 命名規則
3. import の書き方
4. モジュール内の並び順
5. 型ヒント
6. 定数とマジックナンバー
7. dataclass・定数クラス・Enum の使い分け
8. getter / setter は書かない
9. デコレーター
10. リソース管理（with 文）
11. 例外
12. ロギング
13. Excel（openpyxl）
14. Windows 操作（pywin32）
15. コメント
16. 日時の扱い
17. テスト

---

## 基本方針

- **Ruff** に準拠する（E/F/W/I/B/UP/SIM/PTH/C4/LOG/G/T20/DTZ/RUF を有効化）
- **型ヒント**を必ず書く
- **マジックナンバー禁止**。数値・文字列定数は名前付き定数にする
- `print` は禁止。ログは `logging` を使う
- コメントは「なぜ」を書く。コードを読めば分かる「何を」は書かない

---

## 命名規則

Python の作法（PEP 8）に従う。

| 種別 | 規則 | 例 |
|---|---|---|
| クラス名 | PascalCase | `Excel`, `LoginPage`, `CsvMerger` |
| 定数・固定値 | UPPER_SNAKE_CASE | `COL_Q`, `SHEET_NAME`, `WAIT_SECONDS` |
| 関数・メソッド | snake_case | `read_rows()`, `run_macro()` |
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

`cfg`（config）、`src`（source）、`tmp`（temporary）は広く定着した慣用略語として許容する。
Excel の変数名は `ws` / `wb` より `worksheet` / `workbook` を推奨する。その他の、意味を
推測しないと読めない略語は避ける。

### 公開メソッドの動詞

同じ操作には同じ動詞を使う。名詞だけのメソッドや、`js()` のように処理が分からない略称は
公開 API に使わない。

| 操作 | 動詞 | 例 |
|---|---|---|
| 処理・マクロ・クエリを実行する | `run_` | `run_macro()`, `run_query()`, `run_task()` |
| データや値を読み取る | `read_` | `read_rows()`, `read_text()`, `read_messages()` |
| 1件を検索する | `find_` | `find_element()` |
| 複数件を絞り込む | `filter_` | `filter_rows()` |
| 存在・状態を判定する | `is_` / `has_` / `can_` | `is_empty()`, `has_element()` |
| 件数を数える | `count_` | `count_elements()` |
| 差分を求める | `diff_` | `diff_row()`, `diff_rows()` |
| 書き込む・保存する | `write_` / `save_` | `write_rows()`, `save_draft()` |
| 末尾へ追加する | `append_` | `append_rows()` |
| 生のスクリプトを実行する | `execute_` | `execute_script()` |

HTTP の `get()`、キー・値ストアの `get()` / `set()` など、その分野で意味が確立している名前は
例外として使ってよい。

### 定数を大文字にする理由

**大文字にすることで「これは変更しない値だ」とコードを読む人が一目で判断できる。**
設定ファイルから読み込んだ値も定数として扱い、大文字で定義する。

```python
# 悪い（変数と区別がつかない）
col_q = 17
sheet_name = "T_data"

# 良い（定数と分かる）
COL_Q = 17
SHEET_NAME = "T_data"
```

config.ini のセクション名・キー名も同じ理由で大文字にする。
Python 側のアクセス（`config.BROWSER.HEADLESS`）と表記が完全に一致するので対応が追いやすい。
**大文字にするのはセクション名とキー名だけ。`=` の右側の値は自由**（小文字・日本語・パスなんでも可）。

```ini
[FILES]
CSV_EAST = 支店A.csv        ; ← 値は自由
OUTPUT_FOLDER = C:\work\out  ; ← 値は自由
```

### セクション名は決まった並びから選ぶ

プロジェクトごとに違う名前を作らない。**同じ値をどこに書くかで迷わない**ようにするため。

| セクション | 中身 | いつ書くか |
|---|---|---|
| `[FILES]` | 入力元・出力先のパス。**フォルダもファイルもここ** | 常に |
| `[CSV]` | CSV の読み書き設定（文字コード・日付書式など） | 使うときだけ |
| `[BROWSER]` | ブラウザの設定（`HEADLESS` など） | 使うときだけ |
| `[CREDENTIALS]` | 認証情報のシステム名（値そのものは DPAPI） | 使うときだけ |
| `[〇〇_MAPPING]` | 列の対応表。ここだけ**キーを実物どおり**に書く | 使うときだけ |

> **`[RUN]` は廃止済み（v0.12.0 / v1.1.0 で完全削除）。** dry-run / debug は
> `with dry_run():` / `with debug():` ブロックで切り替える。**環境変数も
> setter も CLI オプションも使わない**（`is_dry_run` / `is_debug` は
> 内部用のみで公開 facade には載せていない）。`config.ini` に `[RUN]` が
> 残っていないかは `ruff` や目視で確認する。

**出力先を `[REPORT]` のような用途名で分けない。** 用途ごとにセクションを作ると、
帳票・集計・退避…と際限なく増え、「今書きたい値はどこか」が毎回変わる。
入出力はまとめて `[FILES]` に置き、`INPUT_` / `OUTPUT_` の接頭辞で区別する。

足りないものが出たら、**セクションを足す前に上のどれかへ収まらないかを見る**。

必須項目は `Config.xxx.yyy` を参照した時点で `ConfigKeyNotFoundError` で
分かる（事前チェック不要）。足りないものを1つずつ見つけて往復させない
のは `with` ブロック内の流れで自然に止まるから。

---

## import の書き方

**どの機能群に依存しているかが import 行で分かる形**にする。
ファイルの先頭を見るだけで依存先が分かり、初めてこのコードを読む人の手がかりにもなる。

| ルール | 理由 |
|---|---|
| 名前を提供するパッケージまで明示して import する | ファイルの先頭だけで依存範囲が分かる |
| **相対 import を使わない**（`from .X` / `from ..X` は禁止） | `from ....exceptions import ...` のようにドットを数えないと依存先が分からない状況を無くす。必ず `from comken.X.Y import Z` のように**パッケージルートからの絶対パス**で書く |
| ワイルドカード import（`import *`）は禁止 | 使っている名前がどこから来たか追えなくなる |
| 並び順は「標準ライブラリ → サードパーティ → 自分のコード」 | Ruff の `I` が自動で整列する |

**相対 import を禁止する理由:** comken は保守する人が Python に詳しいとは限らないので、
「短く賢いコード」より「半年後に読めるコード」を取る。`from .foo` / `from ..foo` / `from ...foo` /
`from ....foo` のように深さで書き分けられると、読むたびにドットを数えて現在のパッケージとの
階層関係を確かめることになる。**深さで使い分けない**（「1個までは相対、2個以上は絶対」の
ような境目は作らない）。**1つの規約に統一する** — 全部絶対 import で書く。

**守られ方:** Ruff の `TID`（flake8-tidy-imports）が
`ban-relative-imports = "all"` で検知する。書き忘れても `ruff check` で落ちる。

## 関数の複雑さ

**長さは測らない。分岐の絡み合いを測る。**

単調に並んでいるコードは長くても読める（GUI の組み立て、引数の検証、表示の整形など）。
読めなくなるのは、**1つの関数が同時にいくつものことをやっている**とき——
進捗を追いながら本来の処理を進める、失敗の種類ごとに違う後始末をする、といった形。

**守られ方:** Ruff の `C90`（mccabe）が `max-complexity = 10` で検知する。
**`select` に `C90` を入れただけでは効かない**（`[tool.ruff.lint.mccabe]` の設定が要る。
2026-08-17 に、有効にしたつもりで動いていないのを見つけた）。

閾値の 10 は「いま全部通る一番きつい値」。これ以上ややこしくなった時点で落ちる。
**引っかかったら、まず「この関数はいくつのことをやっているか」を数える。**
たいてい2つ以上あり、分ければ複雑さも一緒に下がる。

```python
# 良い（機能を提供するパッケージが分かる）
from パッケージ.excel import Excel

# 悪い（どの機能群に依存しているか分からない）
from パッケージ import Excel, DateFileFinder

# 悪い（ドットを数えないと依存先が分からない）
from ..foo import Bar
from ....exceptions import BazError

# 悪い（使う名前と依存範囲が分からない）
from パッケージ.utils.files import *
```

> comken のどの名前を import してよいかは [README「使うときの約束」](../../README.md#使うときの約束)、
> 本体側で何を公開するかは
> [ライブラリ開発規約](ライブラリ開発規約.md#公開-api-の管理) を参照。

---

## モジュール内の並び順

「上から順に読めば、重要なものから細部へ進む」新聞スタイルで統一する。
レビューや読解のとき、ファイルの前半だけで全体像がつかめる。

| 順番 | 置くもの |
|---|---|
| 1 | モジュール docstring（1行目は `パッケージルートからの相対パス.py — 役割`、続けて背景・使い方） |
| 2 | import |
| 3 | `logger`・型変数（`TypeVar` / `ParamSpec`） |
| 4 | 定数・定数クラス |
| 5 | 主役の公開クラス（モジュール名が指すもの） |
| 6 | その他の公開クラス・公開関数 |
| 7 | 内部ヘルパー（`_` プレフィックス）— **必ず最後** |

```python
"""example/handler.py — ○○ユーティリティ"""            # 1. docstring
import logging                          # 2. import

logger = logging.getLogger(__name__)    # 3. logger

DEFAULT_TIMEOUT = 30                    # 4. 定数

class CSV:                        # 5. 主役の公開クラス
    ...

def merge_csv(paths: list) -> Path:     # 6. 公開関数
    ...

def _detect_encoding(path: Path) -> str:  # 7. 内部ヘルパー
    ...
```

**例外:** クラス属性の初期化（クラス本体）が import 時に呼ぶヘルパーは、
Python の実行順の都合でそのクラスより上に置くしかない。
その場合は `# NOTE:` コメントで「クラス定義時に使うため上に置く」と理由を書く。

---

## 型ヒント

すべての関数に引数・戻り値の型ヒントを付ける。

```python
# 悪い（型が分からない）
def find_latest(folder, pattern="*.xlsx"):
    ...

# 良い
def find_latest(folder: str | Path, pattern: str = "*.xlsx") -> Path | None:
    ...
```

| よく使う型ヒント | 意味 |
|---|---|
| `str \| None` | 文字列または None |
| `Path \| str` | Path オブジェクトまたは文字列 |
| `list[dict]` | 辞書のリスト |
| `dict[str, list]` | キーが文字列、値がリストの辞書 |
| `X \| None` | `Optional[X]` の代わりに使う（Python 3.11+） |

- 原則として `Any` は使わず、具体的な型を付ける。
- ただし、COM オブジェクト、Excel セル値、型情報を提供しない外部ライブラリとの境界など、
  正確な型を現実的に表せない動的境界では `Any` を最小限の範囲に限って許容する。
  `Any` を通常のアプリケーションロジックへ伝播させず、境界の内側で具体型へ変換する。
- `from __future__ import annotations` は全ファイルには入れず、前方参照、循環 import の回避、
  `TYPE_CHECKING` 内だけで import する名前を型注釈に使う場合など、注釈の遅延評価が必要な
  ファイルにだけ入れる。残す場合は、必要な理由を import の直前にコメントで書く。

---

## 定数とマジックナンバー

コードの中に突然出てくる意味不明な数値や文字列を**マジックナンバー**と呼ぶ。

```python
# 悪い例（マジックナンバー）
rows = f.read_rows("売上データ", min_row=2)
if file_size > 10485760:
    ...
```

```python
# 良い例（名前付き定数）
SHEET_NAME = "売上データ"
HEADER_ROW = 1
LOCAL_COPY_THRESHOLD_MB = 10
LOCAL_COPY_THRESHOLD_BYTES = LOCAL_COPY_THRESHOLD_MB * 1024 * 1024  # 計算式のまま書く

rows = f.read_rows(SHEET_NAME, min_row=HEADER_ROW + 1)
if file_size > LOCAL_COPY_THRESHOLD_BYTES:
    ...
```

| ルール | 詳細 |
|---|---|
| **大文字スネークケース** | `SHEET_NAME`, `MAX_RETRY_COUNT` |
| **場所** | ファイルの先頭またはクラスの先頭（メソッドより上）にまとめる |
| **計算式はそのまま書く** | `10 * 1024 * 1024`（`10485760` より意味が伝わる） |
| **選択肢を渡す引数は定数クラスを使う** | `CSV(encoding=Encoding.CP932)`, `set_fill(color=Color.RED)`。生の文字列（`encoding="cp932"`）はマジックナンバーになるので書かない |

---

## dataclass・定数クラス・Enum の使い分け

まず結論の早見表。迷ったらこれを見る。

| やりたいこと | 使うもの | 例 |
|---|---|---|
| 決まった値の一覧を名前で持つ（インスタンスを作らない） | ただのクラス属性（**定数クラス**） | `Color.RED`, `Encoding.CP932` |
| 複数の値をひとまとまりで持ち運ぶ「データの箱」 | `@dataclass` | 集計結果・検索結果など、名前付きの値のセットを返すとき |
| 振る舞い（メソッド）が主役のもの | 普通のクラス | `Excel`, `DateFileFinder` |

### 定数クラス — 「変わらない値の一覧」を入れる箱

インスタンス（`Color()`）は作らない。クラスにぶら下げた属性を `Color.RED` のように**そのまま読む**だけ。
選択肢を引数で渡すとき、生の文字列（`"FF0000"`）を書かずに名前で渡すために使う。

```python
class Color:
    RED = "FF0000"
    YELLOW = "FFFF00"

cell.fill = Color.RED   # ← "FF0000" と書くより意味が明確。typo は AttributeError で即発覚
```

- 中身は「振る舞い」ではなく「値の表」。だから `@dataclass` も `__init__` も要らない。
- `enum.Enum` を使う手もあるが、値を取り出すのに `Color.RED.value` と `.value` が要るなど
  初学者に一手間多い。**この規約ではプレーンなクラス属性を使う**（typo が即エラーになる Enum の利点は
  クラス属性でも同じ）。

### dataclass — 「名前付きの値のセット」を持ち運ぶ箱

`@dataclass` を付けると、`__init__`（初期化）・`__repr__`（print 表示）・`__eq__`（== 比較）を
**自動で書いてくれる**。「3個以上の値をまとめて返したい」ときに、dict やタプルより型が明確で読みやすい。

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass
class ReportSummary:
    output_path: Path
    matched: int
    skipped: int

result = ReportSummary(Path("out.xlsx"), matched=120, skipped=3)
result.matched          # → 120（result["matched"] より typo に強い・IDE 補完が効く）
print(result)           # → ReportSummary(output_path=..., matched=120, skipped=3) と自動で見やすく出る
```

- 返す値が **2個まで**ならタプルでよい（`return output_path, matched`）。**3個以上**になったら dataclass を検討する。
- 「データの箱」であって「振る舞いの主役」ではない。ロジックが増えてきたら普通のクラスにする。

### frozen — 「作った後は変えさせない」dataclass

`@dataclass(frozen=True)` にすると、**作った後にフィールドを書き換えられなくなる**（読み取り専用）。
うっかり値を上書きする事故を防げるので、**「一度作ったら変わらない値のセット」には frozen を付けるのが安全**。

```python
@dataclass(frozen=True)
class Fee:
    rate: float
    label: str

fee = Fee(0.1, "消費税")
fee.rate          # 読むのは OK → 0.1
fee.rate = 0.08   # ✗ FrozenInstanceError（書き換えようとすると実行時エラーになる）
```

frozen を付けるとうれしいこと:

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

---

## getter / setter は書かない

Java 風の `get_x()` / `set_x()` は使わない。
`@property` は原則使わない。ただし**外部から上書きさせたくない属性の読み取り専用公開**には使ってよい。

```python
# 悪い（Java 風 getter）
class DownloadDir:
    def get_path(self): return self._path

# 悪い（計算値のラップに @property を使う）
class AppConfig(Config):
    @property
    def csv_east_path(self) -> Path:
        return Path(self.FILES.INPUT_FOLDER) / self.FILES.CSV_EAST

# 良い（直接アクセス）
dl = DownloadDir()
print(dl.path)

# 良い（計算値はインラインで書く）
path = config.FILES.CSV_INPUT_FOLDER / config.FILES.CSV_EAST

# 良い（上書きさせたくない属性の公開に @property を使う）
class BrowserSession:
    @property
    def raw(self) -> webdriver.Edge:
        return self._driver  # 外部から raw = xxx と上書きさせない
```

`@property` の使い分け:

| 場面 | 方針 |
|---|---|
| 計算値（パス組み立て等） | インラインで書く |
| 複数箇所で使う計算値 | モジュールレベル定数に入れる |
| 呼ぶたびに処理が走ることを明示したい | 普通のメソッド |
| 書き換えてほしくない内部属性の公開 | `@property`（読み取り専用として公開）|

---

## デコレーター

**使わないのが基本方針。** 明確な必要性がない限り使わない。

| デコレーター | 方針 |
|---|---|
| `@property` | 原則使わない。外部から上書きさせたくない属性の読み取り専用公開に限り使ってよい |
| `@staticmethod` | 原則モジュールレベル関数にする。クラスと概念的に切り離せない場合は使ってよい |
| `@classmethod` | ファクトリメソッド（別コンストラクタ）にだけ使う |
| `@cache` / `@lru_cache` | 使わない。状態はインスタンスで持つ |
| カスタムデコレーター | 書かない |
| `@dataclass` | [dataclass・定数クラス・Enum の使い分け](#dataclass定数クラスenum-の使い分け) 参照 |

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

## リソース管理（with 文）

ファイル・ドライバー・COM オブジェクトは必ず `with` 文または `try/finally` で確実に解放する。

| 方法 | 挙動 |
|---|---|
| `with` 文 | ブロックを抜けると自動で `close()`（例外が起きても確実に閉じる） |
| 手動 `close()` | 途中で例外が起きると実行されない → ファイルが開きっぱなし |

```python
# 良い（with 文）
with Excel("data.xlsx") as f:
    rows = f.read_computed_rows_as_dicts("Sheet1")

# with が使えない場合（pywin32 の COM オブジェクト等）
excel = None
try:
    excel = win32com.client.Dispatch("Excel.Application")
    # 処理
finally:
    if excel:
        excel.Quit()
```

Excel ファイルが開きっぱなしになると、次に開こうとしたときに「ファイルが使用中」エラーになる。

---

## 例外

固有の失敗にはカスタム例外を使い、**基底例外を1つ決めて、その下に階層化する**。
呼び出し側が基底1つで「自分たちのコード由来の失敗」をまとめて捕捉できるようにするため。

| ルール | 理由 |
|---|---|
| 素の `Exception` を投げない。ライブラリ固有の失敗にはカスタム例外を使う | 呼び出し側で「どのエラーか」を判別できるようにする |
| 1つの失敗に1つの個別例外クラスを割り当てる | 例外の型だけで失敗内容が分かり、個別に捕捉できるようにする |
| メッセージは個別例外の `__init__` で組み立てる | 送出側に文面の組み立てを散らさない |
| メッセージには「何が・どこで・どうすればよいか」を含める | 非エンジニアがエラー画面を読んで対処できるようにする |
| 例外は握りつぶさない（`except: pass` は禁止） | 失敗を隠すと原因究明ができなくなる |

`FileNotFoundError`（ファイル不在）、`TimeoutError`（待機時間超過）、`ValueError`（標準的な引数の検証）は、
呼び出し側が一般的な Python の例外として扱えるよう、そのまま送出してよい。
ただし `Exception` を直接送出してはならない。

### try / except での受け取り方

捕捉する粒度は、対応の細かさに合わせて3段階から選ぶ。細かい方から順に `except` を並べる
（先に基底を書くと、下位の例外がそこで捕まって個別の対応に届かない）。

| except の粒度 | 使いどころ |
|---|---|
| 個別の例外 | そのエラーだけ個別に対応したいとき |
| カテゴリの基底 | ある分野のエラーをまとめて処理したいとき |
| ライブラリの基底 | ライブラリ由来のエラーを全部キャッチしたいとき |

> comken の例外階層の全体像は [仕様書「例外体系」](仕様書.md#5-例外体系)、
> 本体へ例外を足すときの設計は
> [ライブラリ開発規約](ライブラリ開発規約.md#カスタム例外の階層設計) を参照。

---

## ロギング

`print` は禁止。必ず `logging` を使う。
**ログの設定（出力先・フォーマット・レベル）は呼び出し元（実行基盤やアプリの入口）が持ち、
ライブラリや個々のモジュールは `logging.getLogger(__name__)` を使うだけ**にする。
モジュール側で設定すると、呼び出し元の設定を黙って上書きしてしまう。

> 単体実行するときの設定の呼び出し方は [README「Logger」](../../README.md#logger) を参照。

```python
import logging

logger = logging.getLogger(__name__)

logger.info("処理開始: %s", file_path)
logger.debug("詳細: %s", value)
logger.warning("ファイルが見つかりません: %s", path)
logger.error("エラーが発生しました", exc_info=True)  # exc_info=True でスタックトレースも出力
```

**`print` を禁止にする理由:**

| | print | logging |
|---|---|---|
| ログレベル（INFO/ERROR 等） | なし | あり |
| ファイルへの出力 | できない | できる |
| 本番環境での抑制 | できない | できる |
| スタックトレースの出力 | 手動で書く | `exc_info=True` で自動 |

---

## Excel（openpyxl）

Excel の読み取りだけなら `Excel`、書き込みを伴う場合は `Excel` を使う。
openpyxl を直接触るのはライブラリにない機能が必要なときだけ。
シートに対する書き込み・書式・構造化テーブル操作は `f.sheet(name)` で取得した
`Sheet` に集約し、`Excel` にはブック単位の操作だけを置く。

### 書式設定は処理ロジックと分離する

```python
from openpyxl.styles import Font, PatternFill, Alignment

def apply_header_style(cell) -> None:
    cell.font = Font(bold=True, color="FFFFFF")
    cell.fill = PatternFill(fill_type="solid", fgColor="4472C4")
    cell.alignment = Alignment(horizontal="center", vertical="center")
```

### 禁止事項

| 禁止 | 理由 |
|---|---|
| `data_only=False` のまま数式セルを上書き | 数式が消える |
| 巨大ファイルをそのまま `load_workbook` | メモリ不足。`read_only=True` を使う |

---

## Windows 操作（pywin32）

### 使用場面

pywin32 は **Windows 固有の API** に限定して使う。
ファイル操作は標準ライブラリの `shutil` / `pathlib` を優先する。

| 用途 | 推奨 |
|---|---|
| ファイルコピー・移動・削除 | `shutil`, `pathlib`（標準） |
| VBA マクロの実行 | `pywin32`（COM 経由） |
| ウィンドウ操作 | `pywin32`（win32gui） |
| レジストリ操作 | `pywin32`（win32api） |

COM オブジェクトは `with` 文が使えないため、`try/finally` で確実に解放する（リソース管理（with 文） 参照）。

### pywin32 の例外

```python
import pywintypes

try:
    pass  # win32 処理
except pywintypes.error as e:
    logger.error("Win32 API エラー: code=%d, msg=%s", e.winerror, e.strerror)
    raise
```

---

## コメント

### 通常コメント

「なぜ」を書く。コードを読めば分かる「何を」は書かない。

```python
# 良い例（なぜを説明している）
# NAS 上の大きなファイルを直接開くと遅く不安定なため、ローカルにコピーしてから開く
if src.stat().st_size > threshold:
    shutil.copy2(src, tmp_path)

# 悪い例（コードを読めば分かる）
i = i + 1  # i に 1 を加算する
rows = f.read_rows()  # 行を読み込む
```

### アノテーションコメント

IDE やエディタが認識する作業メモ用のタグ。`# タグ: 内容` の形式で書く。

| タグ | 意味 | 使いどころ |
|---|---|---|
| `TODO` | あとで追加・修正すべき | 未実装の機能、後回しにしたこと |
| `FIXME` | 既知の不具合がある | 動くが正しくない箇所 |
| `HACK` | きれいでない実装 | 暫定対応、リファクタリングが必要 |
| `XXX` | 危険・動く理由が不明 | 触ると壊れそうな箇所 |
| `REVIEW` | 動作確認が必要 | 意図通りか怪しい箇所 |
| `OPTIMIZE` | パフォーマンス改善が必要 | ボトルネックになっている箇所 |
| `NOTE` | なぜこうなったかの説明 | 仕様上の制約・背景情報 |
| `WARNING` | 注意が必要 | 副作用・前提条件がある箇所 |
| `CHANGED` | どう変更したかの記録 | 変更履歴をコードに残したいとき |

```python
# TODO: エラー時のリトライ処理を追加する
# FIXME: 列数が0のとき IndexError になる
# HACK: openpyxl のバグで数式が壊れるため、保存前に一時的に無効化する
# NOTE: この関数は NAS パスのみ対応。ローカルパスは local_copy() を使うこと
# WARNING: この処理はファイルを上書きする。バックアップを取ってから実行すること
```

### 特殊コメント（ツール向け）

ツールが解釈する「魔法のコメント」。コードの動作ではなくツールの挙動を制御する。

#### `# noqa` — リント警告を抑制する（Ruff / flake8）

```python
from module import something  # noqa: F401  # F401 = インポート未使用の警告を無視
x = 1+1  # noqa: E226  # E226 = スペースなし演算子の警告を無視
```

#### `# type: ignore` — 型チェックエラーを抑制する（mypy / pyright）

```python
result = some_func()  # type: ignore[return-value]  # 返り値の型が合わないが意図的
value = d.get("key")  # type: ignore[assignment]  # None になり得るが確認済み
```

#### `# fmt: off` / `# fmt: on` — フォーマッターを一時的に無効化する

```python
# fmt: off
matrix = [
    1, 0, 0,
    0, 1, 0,
    0, 0, 1,
]
# fmt: on
```

#### `# pragma: no cover` — カバレッジ計測から除外する（pytest-cov）

```python
if __name__ == "__main__":  # pragma: no cover
    main()
```

#### 使い方の原則

| ルール | 理由 |
|---|---|
| 必ず理由もコメントに書く | 「なぜ抑制しているか」が後で分からなくなる |
| `# noqa`（エラーコードなし）は乱用しない | 本物のバグも一緒に隠してしまう |
| できるだけ根本原因を修正する | 特殊コメントは最終手段 |

---

## 日時の扱い

- 現在時刻・今日の日付は共通の `now()` / `today()`（`comken`）を使い、
  `datetime.datetime.now()` / `datetime.date.today()` を直接呼ばない。
  タイムゾーンの扱いを1か所に集め、テストで時刻を差し替えられるようにするため
  （素の `now()` は Ruff の `DTZ` でも検出される）。
- CSV・ファイル名・帳票などの業務日付は `datetime.date` のまま扱い、
  タイムゾーンを付けない。
- 経過時間の計測は `time.perf_counter()`（`Timer` / `measure`）を使う。

---

## テスト

テストは**参考パターン**として。書き方を知っておくと後で助かる。

### ファイル構成

```
tests/
  __init__.py
  test_config.py
  test_csv.py
  test_utils.py
```

### 書き方のパターン

```python
class TestCSVFind:
    def test_finds_existing_row(self, sample_csv):
        """キーに一致する行を返す。"""
        row = CSV(sample_csv).find("注文番号", "A001")
        assert row is not None
        assert row["金額"] == "1000"

    def test_returns_none_when_not_found(self, sample_csv):
        """見つからない場合は None を返す。"""
        row = CSV(sample_csv).find("注文番号", "Z999")
        assert row is None
```

| ルール | 例 |
|---|---|
| テストクラス名は `Test` + 対象クラス名 | `TestExcel`, `TestCSV` |
| テストメソッド名は `test_` + 何を確認するか | `test_returns_none_when_not_found` |
| 一時ファイルは `tmp_path` フィクスチャを使う | `def test_something(tmp_path):` |
