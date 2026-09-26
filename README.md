# comken

業務自動化で使う Python 共通ライブラリ。

動作環境: Windows / Python 3.13 以上（実行環境は 3.14）。詳細は [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) の「9. 動作環境」。

設計は [設計書](docs/ARCHITECTURE.md) を参照。

## はじめて使う人へ

この README を最初から最後まで読む必要はない。次の順で進めるのが早い:

1. **プロジェクトの準備**（下の「プロジェクトの準備」節。起動用バッチに共有ライブラリの場所を設定）
2. **やりたいことを「モジュール一覧」から探す** → その節のコード例をコピーして動かす
3. **動くサンプルを見る** → `examples/`（一覧は examples/README.md。CSV→Excel レポート・
   突合転記・差分レポートはインストール直後にそのまま動かせる。新規ツールの雛形もここ）
4. **エラーが出たら** → ERRORS.md（メッセージに対処法が書いてある）

最初の1本はこれだけで書ける（CSV を読んで Excel レポートを作る例）:

```python
from comken.toolbox.csv import CSV
from comken.toolbox.excel import Excel

with CSV(r"C:\作業\data.csv", read_only=True) as csv_file:
    table = csv_file.read()

with Excel(r"C:\作業\report.xlsx") as excel:
    excel.create_data_sheet("結果").create_table("結果", table)
```

## ドキュメントの地図

この README がすべての入口です。目的に合う行から読み始めてください。

| したいこと | 読むもの |
|---|---|
| はじめて使う | この README の「[はじめて使う人へ](#はじめて使う人へ)」 |
| 何が用意されているか探す | このREADMEの「[モジュール一覧](#モジュール一覧)」 |
| モジュールの使い方を知る | [CSV](docs/機能/csv.md)・[Excel](docs/機能/excel.md)・[Access](docs/機能/access.md)・[Outlook](docs/機能/outlook.md)・[Windows](docs/機能/windows.md)・[ブラウザ](docs/機能/browser.md)・[Salesforce](docs/機能/salesforce.md)・[core の部品](docs/機能/core.md)・[認証情報](docs/機能/credentials.md)・[祝日・営業日判定](docs/機能/holidays.md)・[Salesforceレポートダウンローダー](docs/機能/salesforce-downloader.md) |
| **初めて外部システムにつなぐ** | ID とパスワードの[登録](docs/機能/credentials.md#登録初回だけ) → [Salesforce につないで確かめる](docs/機能/salesforce.md#つないで確かめるコマンド) |
| 引数・戻り値・例外を正確に知る | [公開 API](docs/自動生成/API.md)（**自動生成**） |
| エラーが出た | [エラー対応ガイド](docs/ERRORS.md)（エラー表は **自動生成**） |
| 動くコードを見る | [examples](examples/README.md) |
| なぜこの設計なのか知る | [設計判断の歴史](docs/HISTORY.md) |
| コードを書く規約 / comken 本体を直す | [CONVENTIONS.md](docs/CONVENTIONS.md)（利用者向け＝1〜14 章、本体編集者向け＝15 章以降） |
| 開発してリリースする | [ARCHITECTURE.md「開発とリリース」](docs/ARCHITECTURE.md#11-開発とリリース)（タグを打つ → 共有サーバーで checkout） |
| comken を使うツールを作る | `python -m comken init プロジェクト名` で雛形を作る（作られた `README.md` が中を案内する） |
| コードを読む・レビューする | [コードを読む順番](docs/CONVENTIONS.md#24-コードを読む順番) |

## 使うときの約束

- **`from comken import ...` で取れるのは、何をするプロジェクトでも使う7個だけ。**
  `config` / `Config`（設定）、`comken_logger`（ログ）、実行モードの2関数
  （`dry_run` / `debug`）、ログの起動元を表す `Backoffice` / `Intranet`
- **部品は `from comken.core import ...` から取る。** ファイル検索・日時・文字列・差分・
  計測など（`FileFinder` / `copy_file` / `project_dir` / `today` / `Timer` / `retry` など。
  正確な数は増減するため固定値を書かない — 知りたいときは
  `python -c "import comken.core; print(len(comken.core.__all__))"`）
- **表データは `CSV` / `Excel` と `Table` を使い、ファイル形式に依存しない処理にする**
  （どの機能群に依存しているかが import 行で分かる）
- **書くときは `from comken import X` が第一選択。** そこに無いものだけ `from comken.core import Y`
- **ファイル・ブラウザ・COM は `with` で開く。** 途中で失敗しても閉じられる
- **エラーは細かい方から受ける。** 個別（`SheetNotFoundError`）→ 分野（`ExcelError`）→
  全体（`ComkenError`）の3段。階層は[例外体系](docs/ARCHITECTURE.md#5-例外体系)
- **機密は config.ini に書かない。** [認証情報](docs/機能/credentials.md)（DPAPI）に入れ、
  config.ini にはキー名だけ書く

## モジュール一覧

| モジュール | 概要 |
|---|---|
| Config | INI ファイルの読み込み |
| DateFileFinder / DateNameBuilder | 日付付きファイルの検索・命名 |
| Transfer | 既存の CSV / Excel クラス間の列マッピング転記 |
| runtime | `with debug():` / `with dry_run():` による実行モード |
| exceptions | comken 固有の例外（エラー名別に対処可能） |
| [CSV](docs/機能/csv.md) | CSV の読み込み・検索・抽出 |
| [Excel（openpyxl）](docs/機能/excel.md) | Excel の読み書き（既存数式の計算結果・マクロは必要時に win32com を使用） |
| [Access](docs/機能/access.md) | Access のマクロ・VBA 実行、テーブル／クエリの CSV 出力 |
| [Outlook](docs/機能/outlook.md) | Classic Outlook の受信メール読み取り・下書き作成 |
| [Windows（pywin32）](docs/機能/windows.md) | Excel COM 操作・ウィンドウ操作・レジストリ読み取り |
| [Browser（Edge）](docs/機能/browser.md) | Edge ブラウザ操作 |
| [Browser 公認サイト](docs/機能/browser.md) | ライブラリ公認の `SiteBase` サブクラスを集めた置き場（`comken.toolbox.browser.sites`）。プロジェクト横断で再利用するサイトだけ昇格する |
| [Salesforce（requests）](docs/機能/salesforce.md) | Salesforce の SOQL・レコード操作・レポート取得・API 使用量の計測 |
| [credentials（DPAPI）](docs/機能/credentials.md) | パスワード・client_secret の暗号化保存（Windows ユーザーに紐付く） |
| [祝日・営業日判定](docs/機能/holidays.md) | 内閣府の祝日 CSV と会社休日ルールを合成した「会社用カレンダー CSV」を Python・VBA 共通で読み取って営業日判定（Excel の WORKDAY 互換） |
| [core（部品）](docs/機能/core.md) | `from comken.core import ...` で取る部品群。ファイル検索・操作・圧縮・ファイル名の組み立て／データ比較・テキスト正規化・待機・リトライ・時間計測・ローカル日時 |
| [Salesforceレポートダウンローダー（services）](docs/機能/salesforce-downloader.md) | 複数プロジェクトのSalesforceレポート定期取得を読み取る側。管理表・履歴・スケジュール・取得実行は `Salesforceレポートダウンローダー` リポジトリ側 |

## 定数クラス一覧

選択肢を渡す引数には生の文字列ではなく、これらの定数を使う。

| 定数クラス | import | 用途 | 例 |
|---|---|---|---|
| `Color` | `from comken.toolbox.excel import Color` | セルの背景色（RGB 16進）。`Sheet.set_background(cell, color)` に渡す | `set_background(cell, Color.RED)` |
| `FileFormat` | `from comken.toolbox.windows import FileFormat` | Excel COM の別名保存形式 | `save_as(path, file_format=FileFormat.CSV)` |

CSV の `encoding` は **`"cp932"` / `"utf-8-sig"` / `"utf-8"` などの Python の codec 名を文字列で渡す**（`CP932` / `sjis` などの書き方の違いは `normalize_encoding` が吸収する）。省略すれば自動判定。

---
## 機能の追加・変更の要望

「この色を `Color` に追加してほしい」など、
**複数のプロジェクトで使えそうな機能は管理者に連絡してください。**

要望の例:

| 種類 | 例 |
|---|---|
| 定数クラスへの値の追加 | `Color` に色を追加したい |
| デフォルト値の変更 | `BrowserOptions` のデフォルトを変えたい |
| ユーティリティの追加 | よく使うファイル操作・文字列変換などを共通化したい |
| 新モジュール | 複数プロジェクトで同じような処理を書いている |

個人プロジェクト固有の処理は各プロジェクト側に書く。
**複数のプロジェクトで繰り返し書いている処理**が追加候補です。

---

## プロジェクトの準備

comken は共有サーバー上の1か所を**直接参照する**（ローカルへのコピー・同期はしない）。

### `PYTHONPATH` は PC イメージ配布で設定済み

会社の PC イメージ配布の時点で `PYTHONPATH` は既に設定されている。利用者が
自分でセットアップする必要はない。

**確認方法**: `python -c "import comken; print(comken.__version__)"` が通るか
確かめる。通れば何もしなくてよい（次の「`python -m comken init` で何が作られるか」まで
読み飛ばしてよい）。

**通らないとき**: これは自分で直すセットアップの問題ではなく、PC の
イメージ配布側の問題。情シス・PC 管理担当へお問い合わせください。
`setup_comken.bat` のような自己解決の手段は無くなった。

### `python -m comken init` で何が作られるか

**打った場所に、プロジェクト名のフォルダが1つ**できる。中身は
`comken/templates/新規プロジェクト/` 一式（パッケージに同梱されている）で、
次の3つが自動で埋まる。

| 埋まるもの | 入るファイル |
|---|---|
| **プロジェクト名** | `main.py`（社内 RPA 基盤へ渡す名前）・`docs/仕様書.md`・`docs/使い方.md` |
| **comken の場所** | `実行.bat`（実行時の `PYTHONPATH`）・`.vscode/settings.json`（補完と定義ジャンプ） |
| — | `README.md` から、ひな形の説明（作り終えたら消す節）が取り除かれる |

```
勤怠集計/
  main.py                  エントリポイント（実行モードの切り替えと例外の受け口）
  src/
    run.py                 ここに処理を書く
  docs/
    使い方.md               業務側の人が読む
    仕様書.md               エンジニアが読む
    ERRORS.md              エラー別の対処
  config.ini.example       設定の見本（config.ini は初回実行時に作られる）
  実行.bat                  起動用（ターミナルから叩く。`pause` 無し＝無人実行向け）
  認証情報の登録.bat          ID・パスワードの登録画面
  .vscode/                 補完と推奨拡張
```

**`config.ini` は作られない。** 初回に `実行.bat` を動かす（または `python main.py` を実行する）と
example からコピーされ、**そこで終了コード 1 で止まる**（値を書き換えないまま本番が動くのを防ぐため）。

### 作ったあと、最初にやること

1. **`実行.bat` を1度動かす**（または `python main.py` を実行する）→ `config.ini` が作られて止まる
2. **`config.ini` を書き換える**。dry-run で動かしたいときは `with comken.dry_run():`
   を `main.py` で `main()` を囲む形にして、まず dry-run で 1 回試す。
   戻しは `with` ブロックを外すだけ
3. **`src/run.py` の `run()` に処理を書く**
4. **`docs/使い方.md`・`docs/仕様書.md` の「（ここを書く）」を埋める**

**comken の場所を後から変えたくなったら**、`実行.bat` と `.vscode/settings.json` の
2つを直す（片方だけ直すと「動くのに補完が効かない」状態になって原因が分かりにくい）。

### プロジェクトごとに設定する

PCの環境変数を変更したくない場合は、各プロジェクトのルートに
`comken/templates/新規プロジェクト/実行.bat` をコピーし、
先頭の`PYTHON_LIBRARY`を共有サーバー上のリポジトリルートに合わせる。この方法ではバッチの実行中だけ`PYTHONPATH`を設定する。
（`python -m comken init` で作ったプロジェクトには、この bat が場所入りで最初から入る）

### bat が何をしているか

`実行.bat` は、この順で動く（`認証情報の登録.bat` は場所を持たず、PC に `PYTHONPATH` が配布済みなのを前提に `python -m comken cred gui` を呼ぶだけ）。

1. **すでに`PYTHONPATH`が通っていれば、そのまま処理に入る**（PC イメージ配布で設定済みのケース）
2. 通っていなければ、bat に書いてある`PYTHON_LIBRARY`を使う
3. そこにも comken が無ければ、**さがした場所を表示して止まる**
   （`PYTHONPATH` が通っていないのはイメージ配布側の問題なので、
    情シスへお問い合わせください）
4. 処理の終了コードを**そのまま返す**。スケジューラや RPA 基盤が成否を判断できる
   （`pause`や`popd`で終わると、失敗しても成功したように見えてしまう）。
   `実行.bat` は RPA が絶対パスで起動する運用もあるので、`pause` を入れていない

### 共有サーバーの comken を更新する

共有サーバーのチェックアウトを、**リリース済みのタグへ切り替える**（→ [開発とリリース](docs/ARCHITECTURE.md#11-開発とリリース)）。

```bat
pushd \\server\share\tools\comken
git fetch --tags
git tag -l                 :: 出ているタグを確認する
git checkout v0.11.3       :: 切り替えたいタグ（上で確認した最新版）
popd
```

**社内固有の値を書いた3ファイルは、切り替えで上書きされないようにしておく。**
配置したときに1回だけ設定する。

```bat
git update-index --skip-worktree comken/toolbox/salesforce/sites/solution_sandbox.py
git update-index --skip-worktree comken/toolbox/salesforce/sites/solution.py
```

これで手元の書き換えが消えず、うっかり push することもない。comken 側でこれらの
ファイルを変更したときは切り替えが止まるので、そのときだけ `--no-skip-worktree` で解除して
手で合わせ、また設定し直す（→ [ARCHITECTURE.md](docs/ARCHITECTURE.md#配置時に書き換える3ファイル)）。

**切り替えた瞬間に、次に import した全プロジェクトが新しい版になる。** 更新のたびの
配布作業はない。問題が出たら前のタグへ戻せば、同じように全プロジェクトが戻る。

- **バイトコードキャッシュは自動でローカルに逃がす**: 共有サーバーが読み取り専用でも
  遅くならないよう、comken は import 時に `.pyc` の出力先を `%LOCALAPPDATA%\comken-pycache`
  に向ける（`sys.pycache_prefix`）。環境変数 `PYTHONPYCACHEPREFIX` を設定済みの場合はそちらを尊重する。
- **代償**: import のたびにネットワークを読むので起動が遅く、共有サーバーが落ちると動かない。
  詳しい仕組み・運用（更新/ロールバック/開発との分離）は [ARCHITECTURE.md「10. パッケージ構成と配置・運用」](docs/ARCHITECTURE.md#10-パッケージ構成と配置運用)を参照。

### comken の場所を変えたとき

comken を別の共有フォルダへ移したときは、各プロジェクトの
`実行.bat` / `.vscode/settings.json` の2か所を新しい場所に書き換える。`python -m comken init` で
作ったプロジェクトではこの2か所は最初から `PYTHON_LIBRARY` で固定されているので、
共有サーバーのパスが変わったときだけ書き換える。bat は cmd.exe に合わせて CP932、
`.vscode/settings.json` は UTF-8（`\\\\` を `\\` に、`\` を `/` に直して書く）。
片方だけ直すと「動くのに補完だけ効かない」状態になり、原因の特定が難しくなる。

