# コーディング規約（Python）

[CONVENTIONS_COMMON.md](CONVENTIONS_COMMON.md)（共通）を読んだ前提で、Python の言語としてのルールを書く。
comken を使うときのルール（import してよい名前・例外・ログ設定・config.ini など）は [CONVENTIONS.md](CONVENTIONS.md) にある。

- **1〜14 章**: Python を書く人全員が守る
- **15 章以降**: ライブラリ（comken 本体など、他のプロジェクトから使われるコード）を書く人だけが追加で守る

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
11. [リソース管理（with 文）](#11-リソース管理with-文)
12. [dataclass・定数クラスの使い分け](#12-dataclass定数クラスの使い分け)
13. [関数の複雑さ](#13-関数の複雑さ)
14. [テスト](#14-テスト)
15. [モジュール内の並び順](#15-モジュール内の並び順)
16. [getter / setter は書かない](#16-getter-setter-は書かない)
17. [デコレーター](#17-デコレーター)
18. [命名・型・dataclass・コメント・例外・ロギングの追補](#18-命名型dataclassコメント例外ロギングの追補)
19. [ツールの設定](#19-ツールの設定)

---

## 1. 基本方針

| ルール | 内容 |
|---|---|
| **Ruff** に準拠する（PEP 8） | 設定は [19 章](#19-ツールの設定)。PEP 8 と食い違う場合はこの規約を優先する |
| **型ヒント**を必ず書く | 引数・戻り値の両方 |
| `print` は禁止 | ログは `logging` を使う |
| 整列用の連続スペースは使わない | 行末コメントは `#` の前に半角スペース2つ |

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

`cfg`（config）、`src`（source）、`tmp`（temporary）は広く定着した慣用略語として許容する。
Excel のブック・シートは `wb` / `ws` と略さず `workbook` / `worksheet` と書く。
その他の、意味を推測しないと読めない略語は避ける。

---

## 3. import の書き方

| ルール | 理由 |
|---|---|
| 名前を提供するパッケージまで明示して import する | ファイルの先頭だけで依存範囲が分かる |
| **相対 import を使わない**（`from .X` / `from ..X` は禁止） | ドットを数えないと依存先が分からない。パッケージルートからの絶対パスで書く |
| ワイルドカード import（`import *`）は禁止 | 使っている名前がどこから来たか追えなくなる |
| 並び順は「標準ライブラリ → サードパーティ → 自分のコード」 | Ruff の `I` が自動で整列する |

```python skip
# 良い
from comken.toolbox.excel import Excel

# 悪い（ドットを数えないと依存先が分からない）
from ..foo import Bar

# 悪い（使う名前と依存範囲が分からない）
from comken.toolbox.utils import *
```

---

## 4. 型ヒント

すべての関数に引数・戻り値の型ヒントを付ける。
型が書いてあれば、関数の中を読まなくても「何を渡して何が返るか」が分かる。

```python
# 悪い（型が分からない）
def find_latest(folder, pattern="*.xlsx"):
    ...

# 良い
def find_latest(folder: str | Path, pattern: str = "*.xlsx") -> Path | None:
    ...
```

- 「無いかもしれない」値は `Optional[X]` ではなく `X | None` と書く
- 原則として `Any` は使わず、具体的な型を付ける（許容範囲は [18 章](#型ヒント)）

---

## 5. 定数とマジックナンバー

マジックナンバーを書かない理由は [共通規約 5 章](CONVENTIONS_COMMON.md#5-意味の分からない数字文字列を直接書かないマジックナンバー禁止)。

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
| **選択肢を渡す引数は定数クラスを使う** | 生の文字列を渡さない（[12 章](#12-dataclass定数クラスの使い分け)） |

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

分岐が増えすぎたら、`elif` / `match` を無理に `if` の羅列に置き換えず、分岐そのものを関数へ切り出す。

---

## 7. 例外

- 例外は握りつぶさない（`except: pass` や、何もしない `except Exception:` は禁止）
- `Exception` を直接送出しない。中身に合った例外を使う
- `FileNotFoundError`（ファイル不在）、`TimeoutError`（待機時間超過）、`ValueError`（引数の検証）は、そのまま送出してよい

comken を使うプロジェクトでどの例外を使うか・独自の例外クラスを作ってよいかは
[CONVENTIONS.md「例外」](CONVENTIONS.md#2-例外)に従う。

---

## 8. ロギング

`print` は禁止。必ず `logging` を使う。

```python
import logging

logger = logging.getLogger(__name__)

logger.info("処理開始: %s", file_path)
logger.debug("詳細: %s", value)
logger.warning("ファイルが見つかりません: %s", path)
logger.error("エラーが発生しました", exc_info=True)  # exc_info=True でスタックトレースも出力
```

メッセージは f-string にせず `%s` で値を渡す（理由とログレベルの選び方は [18 章](#ロギング)）。
実行するときのログの設定は [CONVENTIONS.md「ロギング」](CONVENTIONS.md#3-ロギング)を参照。

---

## 9. コメント

「なぜ」を書く（[共通規約 6 章](CONVENTIONS_COMMON.md#6-コメントにはなぜを書く)）。

```python
# 良い例（なぜを説明している）
# NAS 上の大きなファイルを直接開くと遅く不安定なため、ローカルにコピーしてから開く
if src.stat().st_size > threshold:
    shutil.copy2(src, tmp_path)

# 悪い例（コードを読めば分かる）
i = i + 1  # i に 1 を加算する
rows = f.to_rows()  # 行を読み込む
```

`# noqa` / `# type: ignore` のような特殊コメントを使うときは、必ずエラーコードと理由もコメントに書く。

```python
from module import something  # noqa: F401  # F401 = インポート未使用の警告を無視
```

---

## 10. 日時の扱い

- 業務の日付（締め日・対象月・ファイル名の日付）は `datetime.date` のまま扱い、タイムゾーンを付けない。文字列のまま計算しない
- 日付を文字列にするときは書式を定数にする（`DATE_FORMAT = "%Y-%m-%d"`）
- 経過時間の計測は `time.perf_counter()` を使う

comken を使うときの「今日の日付」の取り方は [CONVENTIONS.md「日時」](CONVENTIONS.md#4-日時)に従う。

---

## 11. リソース管理（with 文）

ファイル・ドライバー・COM オブジェクトは `with` 文で確実に解放する。途中でエラーが起きても自動で閉じられる。

```python
# 良い
with open(path, encoding="utf-8") as file:
    text = file.read()
```

`with` が使えないもの（pywin32 の COM オブジェクトなど）は `try` / `finally` で解放する。

```python
excel = None
try:
    excel = win32com.client.Dispatch("Excel.Application")
    ...
finally:
    if excel is not None:
        excel.Quit()
```

---

## 12. dataclass・定数クラスの使い分け

| やりたいこと | 使うもの | 例 |
|---|---|---|
| 決まった値の一覧を名前で持つ（インスタンスを作らない） | ただのクラス属性（定数クラス） | `Color.RED`, `FileFormat.CSV` |
| 複数の値をひとまとまりで持ち運ぶ「データの箱」 | `@dataclass` | 集計結果・検索結果など |
| 振る舞い（メソッド）を持つもの | 普通のクラス | `Excel`, `FileFinder` |

```python
class Color:
    RED = "FF0000"
    YELLOW = "FFFF00"

cell.fill = Color.RED   # "FF0000" と書くより意味が明確
```

- `Enum` は使わない（理由は [18 章](#dataclass定数クラスenum)）
- 返す値が **2個まで**ならタプルでよく、**3個以上**になったら `@dataclass` を検討する

---

## 13. 関数の複雑さ

**長さは測らない。分岐の絡み合いを測る。**

単調に並んでいるコードは長くても読める（GUI の組み立て、引数の検証、表示の整形など）。
読めなくなるのは、**1つの関数が同時にいくつものことをやっている**とき——
進捗を追いながら本来の処理を進める、失敗の種類ごとに違う後始末をする、といった形。

**守られ方:** Ruff の `C90`（mccabe）が `max-complexity = 10` で検知する。
**`select` に `C90` を入れただけでは効かない**（`[tool.ruff.lint.mccabe]` の設定が要る。[19 章](#19-ツールの設定)）。

**引っかかったら、まず「この関数はいくつのことをやっているか」を数える。**
たいてい2つ以上あり、分ければ複雑さも一緒に下がる。

---

## 14. テスト

テストは参考パターンとして。書き方を知っておくと後で助かる。

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

## 16. getter / setter は書かない

Java 風の `get_x()` / `set_x()` は使わない。属性に直接アクセスする。
`@property` は原則使わない。ただし**外部から上書きさせたくない属性の読み取り専用公開**には使ってよい。

```python skip
# 良い（上書きさせたくない属性の公開に @property を使う）
class BrowserSession:
    @property
    def raw(self) -> webdriver.Edge:
        return self._driver  # 外部から raw = xxx と上書きさせない
```

| 場面 | 方針 |
|---|---|
| 計算値（パス組み立て等） | インラインで書く |
| 複数箇所で使う計算値 | モジュールレベル定数に入れる |
| 呼ぶたびに処理が走ることを明示したい | 普通のメソッド |
| 書き換えてほしくない内部属性の公開 | `@property`（読み取り専用として公開）|

---

## 17. デコレーター

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

## 18. 命名・型・dataclass・コメント・例外・ロギングの追補

ライブラリを書くときに 1〜14 章へ追加で必要になる規則。

### 命名

#### 略語の扱い（クラス名・例外名）

PEP 8 は CapWords の中で略語を使う場合、**略語の文字をすべて大文字にする**よう推奨している:

> When using abbreviations in CapWords, capitalize all the letters of the abbreviation.
> Thus `HTTPServerError` is better than `HttpServerError`.

**クラス名・例外名に限り、略語はすべて大文字にする。** 表記の揺れを残さないため、
同じ略語の小文字始まりと全大文字が文書内で混ざらないよう統一する。

| 種別 | 例 | 備考 |
|---|---|---|
| 一般的な略語（クラス名） | `CSVError`, `APIMetrics`, `ExcelCOMHandler`, `HolidayError` | すべて大文字 |
| 複合語の略語（例外名） | `SalesforceReportIDNotFoundError`, `SalesforceReportTruncatedError` | `ID` も2文字だが大文字 |
| 固有名詞・ブランド名 | `OAuth`, `DPAPI`, `HTTP` | 固有名詞としての表記をそのまま使う（例: `RefreshTokenOAuth`） |

snake_case の世界（関数名・変数名・モジュール名・パッケージ名・config キー）は PEP 8
に従い**略語を小文字のまま**にする。`api_key` を `API_KEY` にしない、`api_usage` を
`APIUsage` にしない。

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

## 19. ツールの設定

comken と同じ Ruff 設定を使う（正本は comken の `pyproject.toml`）。要点:

```toml
[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "SIM", "PTH", "C4", "C90", "LOG", "G", "T20", "DTZ", "RUF", "TID"]
ignore = [
    # 日本語のコード・コメント・docstring を「紛らわしい文字」として大量に誤検知するため
    "RUF001", "RUF002", "RUF003",
]

[tool.ruff.lint.flake8-tidy-imports]
# 相対 import 禁止（3 章）
ban-relative-imports = "all"

[tool.ruff.lint.mccabe]
# 分岐の絡み合いの上限（13 章）。select に C90 を入れても、ここが無いと効かない
max-complexity = 10
```

VS Code では拡張機能「Ruff」を入れ、保存時に整形されるようにする（`.vscode/settings.json`）。

```json
{
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.fixAll.ruff": "explicit",
      "source.organizeImports.ruff": "explicit"
    }
  },
  "editor.rulers": [100]
}
```
