# original_libs

業務自動化で使う Python 共通ライブラリ。

## はじめて使う人へ

この README を最初から最後まで読む必要はない。次の順で進めるのが早い:

1. **プロジェクトの準備**（下の「プロジェクトの準備」節。起動用バッチに共有ライブラリの場所を設定）
2. **やりたいことを「モジュール一覧」から探す** → その節のコード例をコピーして動かす
3. **動くサンプルを見る** → `examples/`（一覧は examples/README.md。CSV→Excel レポート・
   突合転記・差分レポートはインストール直後にそのまま動かせる。新規ツールの雛形もここ）
4. **エラーが出たら** → ERRORS.md（メッセージに対処法が書いてある）

最初の1本はこれだけで書ける（CSV を読んで Excel レポートを作る例）:

```python
from comken.csv import CsvReader
from comken.excel import ExcelWriter

rows = CsvReader(r"C:\作業\data.csv").rows()      # CSV を読む（1行 = 1辞書）

with ExcelWriter.create(r"C:\作業\report.xlsx") as f:  # 新規 Excel を作る
    s = f.sheet("Sheet1")
    s.write_table(rows)                            # ヘッダー + データをまとめて書く
    s.auto_width()                                 # 列幅を整える
    s.freeze_header()                              # 1行目を固定
    f.save()
```

**関連ドキュメント**:

- 設計方針・ユースケース: 仕様書.md（管理者・設計を知りたい人向け）
- コーディング規約（共通）: CONVENTIONS.md（すべての Python コード）
  - comken 本体を編集する人: docs/ライブラリ開発規約.md
  - comken を使うプロジェクトを作る人: docs/プロジェクト規約.md
- エラーが出たときの対応: ERRORS.md（プロジェクトに配る雛形）
- 用途別の関数一覧（何が用意されているか）: docs/機能カタログ.md
- コードレビュー・読解する人向け: docs/コードリーディングガイド.md（全体地図と読む順番）

## モジュール一覧

| モジュール | 概要 |
|---|---|
| Config | INI ファイルの読み込み |
| runtime | `with debug():` / `with dry_run():` による実行モード |
| constants | CSV・Excel・ファイル検索で使う公開定数 |
| exceptions | comken 固有の例外（エラー名別に対処可能） |
| [CSV](docs/CSV操作.md) | CSV の読み込み・検索・抽出 |
| [Excel（openpyxl）](docs/Excel操作.md) | Excel の読み書き（既存数式の計算結果・マクロは必要時に win32com を使用） |
| [Access](docs/Access操作.md) | Access のマクロ・VBA 実行、テーブル／クエリの CSV 出力 |
| [Outlook](docs/Outlook操作.md) | Classic Outlook の受信メール読み取り・下書き作成 |
| [Windows（pywin32）](docs/Windows操作.md) | Excel COM 操作・ウィンドウ操作・レジストリ読み取り |
| [Browser（Edge）](docs/ブラウザ操作.md) | Edge ブラウザ操作 |
| [Salesforce（requests）](docs/Salesforce.md) | Salesforce の SOQL・レコード操作・レポート取得・API 使用量の計測 |
| [credentials（DPAPI）](docs/認証情報.md) | パスワード・client_secret の暗号化保存（Windows ユーザーに紐付く） |
| [utils.files](docs/ファイル操作.md) | ファイル検索・操作・圧縮・標準フォルダ取得・ファイル名の組み立て |
| [utils](docs/ファイル操作.md) | データ比較・テキスト正規化・待機・リトライ・時間計測・ローカル日時取得 |

## 定数クラス一覧

選択肢を渡す引数には生の文字列ではなく、これらの定数を使う。

| 定数クラス | import | 用途 | 例 |
|---|---|---|---|
| `Color` | `from comken.constants import Color` | セルの背景色 | `set_fill(color=Color.RED)` |
| `SortBy` | `from comken.constants import SortBy` | FileFinder.latest の並び順 | `latest(by=SortBy.UPDATED)` |
| `Encoding` | `from comken.constants import Encoding` | CSV の文字コード | `CsvReader(path, encoding=Encoding.CP932)` |
| `FileFormat` | `from comken.constants import FileFormat` | Excel COM の別名保存形式 | `save_as(path, file_format=FileFormat.CSV)` |

---

## 機能の追加・変更の要望

「このエンコーディングを `Encoding` に追加してほしい」「この色を `Color` に追加してほしい」など、
**複数のプロジェクトで使えそうな機能は管理者に連絡してください。**

要望の例:

| 種類 | 例 |
|---|---|
| 定数クラスへの値の追加 | `Encoding` に新しい文字コード、`Color` に色を追加したい |
| デフォルト値の変更 | `BrowserOptions` のデフォルトを変えたい |
| ユーティリティの追加 | よく使うファイル操作・文字列変換などを共通化したい |
| 新モジュール | 複数プロジェクトで同じような処理を書いている |

個人プロジェクト固有の処理は各プロジェクト側に書く。
**複数のプロジェクトで繰り返し書いている処理**が追加候補です。

---

## プロジェクトの準備

comken は共有サーバー上の1か所を**直接参照する**（ローカルへのコピー・同期はしない）。
各プロジェクトのルートに `templates/実行.bat` をコピーし、先頭の `COMKEN_ROOT` を
共有サーバー上の comken リポジトリルートに合わせる。バッチは実行中だけ `PYTHONPATH` を設定するため、
PC の環境変数を変更しない。

```bat
set "COMKEN_ROOT=\\server\share\tools\comken"
set "PYTHONPATH=%COMKEN_ROOT%;%PYTHONPATH%"
python main.py
```

以後、どのプロジェクトからでも `import comken` が共有サーバーの最新版を読む。更新のたびの配布作業はない。
（共有サーバーの comken を更新すれば、次に import した全プロジェクトが最新になる）

- **バイトコードキャッシュは自動でローカルに逃がす**: 共有サーバーが読み取り専用でも
  遅くならないよう、comken は import 時に `.pyc` の出力先を `%LOCALAPPDATA%\comken-pycache`
  に向ける（`sys.pycache_prefix`）。環境変数 `PYTHONPYCACHEPREFIX` を設定済みの場合はそちらを尊重する。
- **代償**: import のたびにネットワークを読むので起動が遅く、共有サーバーが落ちると動かない。
  詳しい仕組み・運用（更新/ロールバック/開発との分離）は 仕様書.md の「参照・運用」を参照。

> 旧方式（robocopy でローカル同期する `初回セットアップ.bat` / `実行.bat` / `リリース.bat`）は
> 直接参照への移行で不要になったため削除済み。

---

## 実行モード（バージョン / デバッグ / dry-run）

```python
import comken

comken.__version__        # → "0.3.0"

# デバッグモード: ライブラリ主要処理（Excel 読み込み・転記・保存、CSV 読み書き、zip 等）の
# 所要時間を DEBUG ログに出す。どこが遅いかの調査に使う
with comken.debug():
    run()

# dry-run モード: 外部に影響する操作を実行せず、内容だけ [DRY-RUN] 付きで INFO ログに出す。
# 読み取り（CSV・Excel の読み込み）は通常どおり実行される
with comken.dry_run():
    run()
```

自作関数の処理時間も同じ仕組みで計測できる（デバッグモード中だけログに出る）:

```python
from comken.utils import measure

@measure
def build_report():
    ...
```

---

## Config

`config.ini` を `config.SECTION.KEY` の形式で読み込む。

**基本の使い方**（`src/config.py` は不要。エディタ補完も効く）:

```python
from comken import config

# 初回アクセス時にカレントディレクトリの config.ini を1度だけ読む（遅延読み込み）
folder = config.REPORT.OUTPUT_FOLDER
path = config.FILES.INPUT_FOLDER / "支店A.csv"

# config.ini が別の場所にある場合は、最初に使う前に読む場所を指定する
config.read(r"C:\作業\config.ini")
```

> **補完（Pylance）:** config を初めて読むと、config.ini から補完用スタブ
> `typings/comken/`（config.pyi + __init__.pyi）が自動生成される。VS Code + Pylance で
> `config.SECTION.KEY` が型付き補完される（typings/ は .gitignore 推奨）。
> ツール実行前にスタブだけ先に作りたいときは `python -m comken.config`。

明示的にインスタンスを持ちたい場合（テストや複数 ini の読み分けに）:

```python
from comken.config import Config

config = Config()                      # カレントディレクトリの config.ini
config = Config("path/to/config.ini")  # パスを指定する場合
```

```ini
; config.ini（プロジェクト固有の非機密設定を書く）
; セクション名・キー名は大文字で書く（固定値と分かる + Python 側と表記が一致する）

[REPORT]
OUTPUT_FOLDER = C:\作業\reports
TEMPLATE_PATH = \\nas-server\templates\template.xlsx
```

```python
config.REPORT.OUTPUT_FOLDER # → str
config.REPORT.TEMPLATE_PATH # → str
```

**列名の対応表:** セクション名を `MAPPING` で終わらせ、`転記元の列名 = 転記先の列名`
の向きで書く。列名は大文字に直されず、値も常に文字列として返る。

```ini
[受注_MAPPING]
受注No = 受注番号
商品cd = 商品コード
年度 = 2026
```

```python
mapping = config.mapping("受注_MAPPING")
# → {"受注No": "受注番号", "商品cd": "商品コード", "年度": "2026"}
```

半角の `:` と `=` は INI の区切り記号になるため、列名には使えない（全角の `：` `＝` は使用可）。

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

まだ一度も実行していない状態で先にスタブだけ作りたい場合は手動で生成できる:

```
python -m comken.config
```

生成された `typings/` は手で編集せず、`.gitignore` に含める（自動生成物）。

なお**ブラウザの設定は config.ini には書かない**。`BrowserOptions` のインスタンス
（`src/browser_options.py`）で行う（Browser を参照）。

---

## State

人が書く固定の設定は `config.ini`、プログラムが次回へ持ち越す状態は `state.ini` と
使い分ける。人が調整した設定をプログラムが上書きする事故を防ぐため、両者は混ぜない。

```python
from comken.state import State

state = State()                         # 実行フォルダ直下の state.ini
last_file = state.get("LAST_FILE")     # 無ければ None
position = state.get("POSITION", 0)    # 既定値も指定できる
state.set("LAST_FILE", "data.csv")    # その場で保存
```

`state.ini` が無い初回実行は空の状態で続行する。値は文字列・数値・bool・文字列リストの
型を保って読み戻せる。壊れたファイルは続きの位置を失わないよう、初回扱いにせずエラーで止まる。
dry-run 中の `set()` はログだけを出し、本番の「処理済み」判定を変えない。

実際に保存される内容:

```ini
[STATE]
LAST_FILE = "data.csv"
POSITION = 42
```

---

## Logger

ログの設定（出力先・フォーマット・レベル）は社内の共通ライブラリ側で行う。
comken と利用プロジェクトは、各モジュールで標準の `logging.getLogger(__name__)` を使うだけでよい。
RPA 基盤を通さず `python main.py` で単体実行するときだけ、先頭で `setup_logging()` を呼ぶ。
明示的に呼んだ場合も、すでに設定済みなら既存のログ設定には触れない。

```python
# main.py（単体実行する場合だけ）
from comken.logger import setup_logging

setup_logging()  # コンソールと logs/YYYY-MM-DD.log（UTF-8）へ出力
# setup_logging(to_file=False)  # コンソールだけに出力する場合
```

```python
# main.py
import logging

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

---

## パッケージ構成

```mermaid
graph LR
    comken --> config["Config\n設定ファイル"]
    comken --> runtime["runtime\n実行モード"]
    comken --> constants["constants\n公開定数"]
    comken --> exceptions["exceptions\n例外体系"]
    comken --> utils["utils\n比較・テキスト・待機・日時"]
    utils --> files["utils.files\n検索・操作・圧縮・パス・命名"]
    comken --> excel["excel\nExcel"]
    comken --> csv["csv\nCSV"]
    comken --> windows["windows\nCOM / Window"]
    comken --> browser["browser\nブラウザ"]
    comken --> salesforce["salesforce\nSalesforce API"]
    salesforce --> sites["salesforce.sites\n組織ごとのクラス"]
    comken --> credentials["credentials\n認証情報（DPAPI）"]
    salesforce --> credentials
```

---

## 主なユースケース

### NAS の Excel を読んで加工・出力する

```mermaid
flowchart LR
    A["NAS\nExcel"] -->|FileFinder.today| B["ファイルパス取得"]
    B -->|ExcelWriter| C["データ読み込み"]
    C --> D["データ加工"]
    D -->|write_cell + save| E["Excel出力"]
```

### CSV を読んで Excel レポートを作る

```mermaid
flowchart LR
    A["CSVファイル"] -->|CsvReader| B["データ読み込み"]
    B -->|filter / index| C["絞り込み・突合"]
    C -->|ExcelWriter| D["Excel書き込み"]
    D --> E["レポート完成"]
```

### ブラウザを自動操作する

```mermaid
flowchart LR
    A["config.ini"] -->|Config| B["設定読み込み"]
    B -->|EdgeDriver| C["ブラウザ起動"]
    C -->|SitePage| D["画面操作"]
```

---

## 改訂履歴

| 日付 | 内容 |
|---|---|
| 2026-07-09 | 初版作成 |
| 2026-07-10 | 全モジュールにドキュメント追加、README 整理 |
| 2026-07-12 | ExcelWriter・ExcelComHandler に `headers` 引数追加（ヘッダーなし Excel 対応）。EdgeDriver のダウンロードフォルダ管理を内部化（デフォルト一時フォルダ・with 終了時自動削除）。`ExcelWriter.transfer_by_key`（openpyxl 版）追加。`diff_row` 追加・`diff_rows` を列単位の差分付きに改良。ExcelComHandler の初期化失敗時に Excel プロセスが残るバグ等を修正 |
| 2026-07-12 | Teams 通知（TeamsNotifier。Power Automate Webhook / Adaptive Card 形式）・テキスト正規化（normalize / strip_spaces / remove_spaces）・待機（wait）・特殊フォルダ取得（Paths）を追加。Paths は OneDrive リダイレクトに追従、通知失敗は TeamsError |
| 2026-07-12 | Config: [a, b, c] 記法でリストに自動変換（parse_list は警告付きで残存）。エディタ補完用スタブ生成（python -m comken.config）を追加。BOM 付き UTF-8 の config.ini が読めないバグを修正 |
| 2026-07-12 | Locator（セレクターのクラス変数管理）・retry・Timer / measure・zip・Excel の Sheet ラッパー（セル参照 / write_table / auto_width / freeze_header）・ExcelWriter.create を追加 |
| 2026-07-12 | comken.__version__ / debug()（主要処理の時間を DEBUG ログに記録）/ dry_run()（外部に影響する操作をスキップ）を追加。EdgeDriver がエラー時に画面を logs/ に自動保存。Excel 孤立プロセス対策（is_excel_running / kill_excel）。リリース.bat で git tag を打つ運用に。スタブ書き込みをアトミック化 |
| 2026-07-13 | ExcelComHandler: 上書き保存 save() 追加、save_as のパスワードが効かない問題を修正（FileFormat を常に明示。形式変換は file_format 引数）、close() でプロセスが残る問題を修正、AskToUpdateLinks=False 追加。CONVENTIONS に「モジュール内の並び順」を追加し全体を整理。docs/（機能カタログ・コードリーディングガイド・設計メモ）を追加 |
| 2026-07-14 | 監査指摘の修正一式（keep_vba・run_macro 保存・DispatchEx・EdgeDriver/SF のリソース解放・config 型変換・CSV/ログの堅牢化・unzip の 3.10 対応/Zip Slip 対策）。コーディング規約を3層（共通/本体/利用側）に分割。配布方式を廃止し共有サーバー直接参照（PYTHONPATH）に変更、同期用 bat（templates/）を削除 |
| 2026-07-15 | `from comken import config` に一本化（src/config.py 不要）。Pylance 補完用 typings スタブを自動生成。当時のログ初期化で comken バージョンを出力。バイトコードキャッシュをローカルに自動退避。examples テスト・README コード構文チェック・CI（GitHub Actions）を追加。新規プロジェクトのひな形 templates/新規プロジェクト/ を追加 |
| 2026-08-13 | **v0.5.0** — 認証情報の暗号化保存を追加（`comken.credentials`）。client_secret・パスワードを Windows DPAPI で暗号化し、`%USERPROFILE%\.comken\credentials.dat` に保管する。登録は対話式ではなく**平文 JSON の取り込み**（`python -m comken.credentials import`）にして、配布時に手入力を挟まない。JSON はシステム名ごとに項目をまとめる形式で、`site_a_client_id` のようなキー名に展開される。書き込みはまとめて1回で、1件でも不正なら1件も保存しない。復号できない場合（登録時と違う Windows アカウント・PC）は原因の確認順を示す `CredentialDecryptionError` にする。`Salesforce.from_credentials()` を追加し、サイトクラスの `CREDENTIAL_PREFIX` から client_id / client_secret を読めるようにした。例外を `CredentialError` 配下に新設 |
| 2026-08-12 | **v0.4.0** — Salesforce 連携を追加（`comken.salesforce`）。認証は OAuth 2.0 クライアントクレデンシャルフローで、リフレッシュトークンを保管しない。1インスタンス=1組織で、組織固有の処理は継承して足す。認証・レポート・計測は継承ではなく合成（JWT フローへ差し替えられるようにするため）。アクセストークンの期限は測らず 401 で1回だけ取り直す。5xx と 429 は待ち時間を伸ばしながら最大3回やり直し、4xx は即エラーにする。レポートは**同期・非同期とも 2000 行が上限**なので、切り捨てを検知したら既定で例外にする（`allow_truncated=True` で警告に落とせる）。API 呼び出しは1か所を通るので、呼び出し元別の回数・リトライ理由・所要時間・`Sforce-Limit-Info` 由来の組織 API 消費量をまとめて記録し、ログと CSV に出せる。例外を `SalesforceError` 配下に新設。依存に requests を追加。docs/Salesforce設計メモ.md・docs/Salesforce_JWTと鍵配布.md を追加 |
| 2026-08-03 | browser を作り直し（**破壊的変更**）。`EdgeDriver` / `BasePage` を廃止し、入口を `Browsers` に一本化（1サイト1ブラウザ・`with` 必須・サイトが1つでも複数でも同じ書き方）。`start` / `wait` で待ち時間に別サイトを進められるようにし、`parallel` はその短縮形に。`Page` を `Locator` 版へ一本化して `click_id` 等の直積メソッドを削除、`elements` を追加。msedgedriver のバージョン不一致を配布フォルダから自動修復。`PROFILE_ROOT` でログイン状態を永続化。ブラウザ例外を `BrowserError` 配下に新設。`py.typed` 追加（補完・型チェック改善）。docs/ブラウザ操作.md・docs/Outlook操作.md を追加 |
