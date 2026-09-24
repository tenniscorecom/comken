# comken 設計書

> この文書は comken の **現在の設計** を書く。
> 経緯・却下した代替案・理由は [`HISTORY.md`](HISTORY.md) を参照する。
> API の使い方（引数・戻り値・例外）は docstring が一次情報で、
> [`自動生成/API.md`](自動生成/API.md) はそこから自動生成される。
> コーディング規約は [`CONVENTIONS.md`](../CONVENTIONS.md) を参照。

## 1. 基本方針

| 方針 | 内容 |
|---|---|
| 可読性最優先 | 短く賢いコードより、半年後に読めるコード。bool 引数よりメソッド名で意味を表す |
| 非エンジニア協業前提 | エラーメッセージに対処法を含める。設定値は config.ini で管理する |
| オフライン環境で動く | 社内 BO 環境では pip が使えない。依存は最小限にし、標準ライブラリを優先 |
| 失敗は早く・明確に | 必要なファイルがなければ即例外。エラーを握りつぶさない |
| YAGNI | 3 箇所で同じ処理が出るまで共通化しない |

個別の設計判断の理由は [`HISTORY.md`](HISTORY.md) に書き、この文書には再録しない。

## 2. レイヤー構成

層は **直下 / core / toolbox / services** の 4 段。

| 層 | 役割 | 主な置き場 |
|---|---|---|
| 直下 | 何にも依存しない共通語彙（例外・定数・実行モード） | `comken/exceptions/`・`comken/constants.py`・`comken/runtime.py` |
| core | 直下にだけ依存する部品（外にあるものを触らない） | `comken/core/` 配下 |
| toolbox | 外にあるもの（Excel・CSV・ブラウザ・Salesforce 等）を触る道具 | `comken/toolbox/` 配下 |
| services | 単一消費者向けの業務シナリオ実装 | `comken/services/`（現在 `salesforce_downloader`） |

依存方向は **下から上にだけ向ける**。上の層は下の層に依存してよいが、下の層は上の層に依存しない。

層の定義と同層依存の例外一覧は **`tests/test_layers.py` を正本** とする。現時点で許可されている同層依存は次の 5 組だけである（許可されていない組を見つけた場合は `ALLOWED_SAME_LAYER` の追加ではなく設計を見直す）。

- `toolbox.excel` ↔ `toolbox.windows`（既存数式・マクロ時の COM フォールバック）
- `toolbox.salesforce` ↔ `toolbox.credentials`（Salesforce 認証情報の安全な保管）
- `toolbox.salesforce` ↔ `toolbox.csv`（CSV/Table への結果変換）
- `toolbox.browser` ↔ `toolbox.salesforce`（レポート API の 2000 行上限の回避）
- `toolbox.browser` ↔ `toolbox.credentials`（DPAPI に保存した ID/パスワードでのログイン）

`comken` 直下には `__all__` で公開する名前だけを集め、深掘りした機能は toolbox / services 配下の深いパスのまま残す（import 行から「どの機能群に依存しているか」が読める）。

`core/` 配下には曖昧な名前のフォルダ（`utils` / `common` / `helpers` / `misc`）を置かない。具体名が立つ単位（`files` / `clock` など）で切る。

外部ライブラリに依存するフォルダは、import 時に対処法つきのエラーを出し、そのフォルダを使わなければ影響しないようにする。

## 3. 公開 API の2階層

| 入口 | 数 | 基準 |
|---|---|---|
| `from comken import ...` | `len(comken.__all__)` | 何をするプロジェクトかに関係なく使う土台 |
| `from comken.core import ...` | `len(comken.core.__all__)` | 特定の操作対象（ファイル・日時・文字列・差分・計測）を持つ部品 |
| `from comken.toolbox.excel import ...` | 各パッケージの `__all__` | 外にあるものを触る道具 |

第一選択は `from comken import X`。そこに無いものだけ `from comken.core import Y` で取る。同じ名前を両方から取れる状態にしない。

公開範囲は **ディレクトリ名ではなく `__all__` で表す**。ディレクトリは「何であるか」で決め、`__init__.py` が公開範囲を決める。公開方針を変えてもファイルが動かない（import パスが壊れない）ようにするためである。

公開／非公開の正本は `tests/test_facade.py`（`__all__` の内容・重複の検査）と `tests/test_layers.py`（層をまたぐ import の向き）。名前の一覧も具体的な数もこの文書には書かない（`README.md` の「モジュール一覧」と同じ数値を 2 箇所に置くと古くなるため）。

新しいクラスを `comken` 直下に追加する基準は「Excel を使わないプロジェクトも通るか」。`Config` が直下、`DateFileFinder` が `core` に置かれているのはこの基準による。

内部実装（基底クラス・転記の内部ヘルパー・一時ファイルの掃除など）はどの階層の `__all__` にも載せない。基底クラス（`FileBase` 等）や内部実装は露出させない。

## 4. 設定と実行モード

### config.ini

`config.ini` は **非エンジニアが自分で変える値だけ** を置く。エンジニアしか触らない固定値は Python コードに書く（プロジェクト名・RPA 基盤へ渡す名前など）。両方を `config.ini` に入れると「触ってよい値」と「触ってはいけない値」が混ざり、渡された人がどれを変えてよいか判断できなくなる。

セクション名・キー名は大文字で書き、Python 側の `config.SECTION.KEY` と表記を一致させる。小文字混じりは読み込み時点で `ConfigLowerCaseNameError` で止める。

機密値（パスワード・トークン・client_secret・refresh_token）は `config.ini` や git には含めず、Windows DPAPI に保管する。`comken.toolbox.credentials` が暗号化保存・読み込み・JSON 取り込みの入口になる。

必須項目を事前チェックする API は持たない。`Config.xxx.yyy` を参照した時点で `ConfigKeyNotFoundError` が止まる。

`config.ini` が無ければ `config.ini.example` からコピーして `ConfigCreatedFromExampleError` で止める。2 回目以降の実行からは通常どおり動く。

### 実行モード

実行モード（`dry_run` / `debug`）の切り替えは **context manager だけ** が受け取る。`config.ini`・環境変数・setter は持たず、`with dry_run():` / `with debug():` ブロックだけが切り替える唯一の手段。

| モード | 振る舞い |
|---|---|
| `dry_run` | 外部影響のある操作（書き込み・送信・コミット）をスキップ。`state.ini` も書き換えない |
| `debug` | `@measure` の開始・完了・中断ログを DEBUG で出す。ブロックを抜ければ静かになる |

`@measure`（`comken.core.timer`）は **業務バッチがどの処理で止まったかを後から特定できる** ことが主目的。関数入口で「開始」、終了時に「完了 ○秒」または「中断 ○秒」を出し、`BaseException` まで捕捉して `raise` で必ず再送出する。引数・戻り値は出さない（DPAPI のトークン・client_secret がログへ載る危険があるため）。

`@measure` を付ける基準は **「外部（ネットワーク・ディスク・別アプリ）を待つか」**。純粋な計算や内部データ加工、ジェネレータ関数には付けない。

### state.ini

`state.ini` は前回処理位置など **プログラムが書く状態** を持つファイルで、`config.ini`（人が書く設定）と分離する。両者を分けると、人が調整した設定をプログラムが上書きする事故を防げる。dry-run 中の `State.set()` はログだけを出して保存しない（本番で処理済みと誤判定されるのを防ぐ）。

INI として壊れたファイルは `StateFileCorruptedError` で止める（前回の続きから再開が静かに失敗するのを防ぐため）。

## 5. 例外体系

すべての例外は **`ComkenError`** を基底とする 1 本の階層。`except ComkenError` でライブラリ由来のエラーをまとめて捕捉できるようにするためである。

- 中間基底（`ExcelError` / `CSVError` / `SalesforceError` 等）は **カテゴリ基底としてまとめて捕捉する用途に限り** 公開する。直接送出しない
- 個別例外は **対処が違う失敗ごとに 1 クラス**（呼び出し側がメッセージ文字列を解析せず、型だけで判別・個別捕捉できるようにする）。対処が同じ失敗は 1 クラスにまとめ、違いはメッセージで示す
- `ComkenFileNotFoundError` は `ComkenError` と標準の `FileNotFoundError` の両方を継承し、Excel・CSV・Config 等のファイルが無い場合をすべて表す（`ExcelError` などのカテゴリ配下ではない）
- 統合して無くなった例外の旧名は残さない（別名も警告も持たない。旧名を使っているコードは `ImportError` になるので、新しいクラスへ書き換える）
- メッセージは「何が・どこで・どうすればよいか」を含める（非エンジニアが読む前提）
- 例外を足すときは `comken/exceptions/__init__.py` の import と `__all__` に必ず追加する
- docstring に「対処:」を書く（`docs/ERRORS.md` はここから生成され、書き忘れると生成が止まって気づける）

例外の継承ツリー・docstring・対処一覧は [`ERRORS.md`](ERRORS.md) と `comken/exceptions/__init__.py` の冒頭 docstring が正本。`tests/test_docs_code.py` が両者の一致と例外総数を検査する。**例外一覧はこの文書に再掲しない**（ここにも書くと片方だけ古くなる）。

素の `ValueError` / `Exception` は投げない。例外は握りつぶさない（`except: pass` は禁止）。行単位の処理エラーは行番号を含めて再送出する。

## 6. Excel の設計方針

Excel は VBA マクロで書かれていた業務の Python 置き換えが主な用途のため、**Excel / VBA と共存する** 設計を取る。

- 読み取りは `Excel(read_only=True)`、書き込みは `Excel`（openpyxl。Excel 不要・高速）
- **comken は数式を自動で入れない**。openpyxl は数式を書けても計算も検証もしないため
- 既存ブックの表は `ExcelTable.read()` で読む。実テーブル内に未計算の数式がある場合だけ COM へ自動昇格し、常に `Table` を返す。再計算を強制する場合は `read(force_com=True)` を使う
- VBA マクロ・パスワード付き保存が必要なときは `ExcelCOMHandler`（COM。Excel 必須）
- 数式・既存マクロ時の COM フォールバックは `toolbox/windows` 側に集約する（過度な抽象化を避けるため、Excel から直接 COM を呼ばない）

シート操作は `Sheet` に集約する。セル書き込み・書式・キー突合転記・構造化テーブルなどシートに対する操作はすべて `Sheet` に置き、ブックに対する操作だけを `Excel` に置く（入口が 2 経路になると一貫性が崩れるため）。

テーブルは **定義を壊さず、中のデータを操作する** 方針で、`ExcelTable` のメソッドも「中のデータを書き換える」操作に限定する。テーブル名変更・削除は持たない（openpyxl では構造化参照が追随せず `#NAME?` になるため）。

Excel / Excel 内の表データ連携は `Transfer(read, write, mapping)` に統一する。CSV / Excel / Access など読み取った `Table` を渡せば、CSV → Excel、Excel → CSV、Excel → Excel、CSV → CSV は同じ API で扱える。形式別の転記クラスは作らない。

`with` を必須とする（読み取り専用でも）。`with` ブロックを外れたインスタンスを触ると `TableNotOpenError` で停止する。`Excel.close()` がローカル作業コピーを削除するため、`with` を使わないと一時ファイルが残り続ける。

ファイル名には拡張子を含める。`ext=` / `extension=` 引数は廃止し、拡張子なしの名前は `FileSuffixMissingError` で止める。

`MasterRow` / `column()` は `comken.services.salesforce_downloader.report_master` に置く Excel の表駆動設定で、読み込み・検証・雛形生成を集約する。`column()` の第 1 引数が見出しになるので、Python 側の命名規約を崩さずスペースを含む見出し（例: `Salesforce URL`）も扱える。列定義の正本は dataclass（`row["名前"]` 形式の辞書アクセスは使わない）。

大きなブックはローカルにコピーしてから開くため、読み込み後に他の PC が元のブックを更新しても検出せずに上書き保存する。複数 PC が同じブックを同時に更新する運用では、プロジェクト側で排他制御を用意する。

## 7. Outlook / Access / Salesforce / ブラウザの現行方針

各機能とも、**メイン業務の過度な抽象化を避ける**。詳細は各機能ドキュメントへリンクする。

### Outlook

- Outlook は **Classic のみ対応**。New Outlook は COM を持たないため自動操作できず、Graph API はオフライン社内では使えない
- 送信は **実装しない**（誤送信が取り消しできないため）。下書き作成までとする
- 受信メールの **添付ファイルを保存・実行する機能と本文中のリンクを開く機能は実装しない**（人が守っている社内ルールを自動処理が迂回しないため）。`MailMessage` が公開するのは `has_attachments` のみ
- `save_draft` でこちら側から添付を付ける操作は **制限しない**（受信物を開く話とは別）
- 添付を保存・展開する名前のメソッドが生えていないことは `tests/test_outlook.py` が検証する

詳細は [`outlook.md`](outlook.md) を参照。

### Access

- ネットワーク越しに直接開くと遅く、排他に阻まれ、接続断で破損しうるため、**既定で `local_copy=True`** でローカルコピーして開く
- Access の整形結果は数十万件になり得るので、Python で全件読み込みはせず、`DoCmd.TransferText` で **Access 自身に CSV を書き出させる** `export_csv()` を主役にする。`rows()` が必要な時だけ使う（内部で COM の往復を減らすバッチ取得を行う）
- 元 DB を更新する場合は `local_copy=False` で元 DB を直接開く。ローカルコピーを書き戻す方式は採らない（他人の更新が DB ごと失われる・速度の利点が消える・最後に排他で失敗して手戻りが最大・大きなファイルの書き戻し中に切断すると DB が壊れる、の 4 つのため）
- 元 DB を直接開く直前に日時付きバックアップを `backup/` へ取り、既定で 7 日間残す。壊れた DB で正常な控えを上書きしないよう同名で上書きせず世代を残す
- 更新結果を共有 DB へ戻すことが目的なら、まず CSV / Excel 別出力・結果専用 DB の分離を検討する

詳細は [`access.md`](access.md) を参照。

### Salesforce

- 業務上の用途は **レポートからデータを引くことが中心** で、レコードの追加・更新は Salesforce 公式の **Data Loader** に任せる
- comken の `insert` / `update` / `upsert` / `delete` は実装済みだが当面は使われない見込み。書き込み側は拡張しない。機能を足すならレポート取得側（2000 行の壁の回避・列名の扱い）に寄せる
- **認証方式**: External Client App + Authorization Code + Refresh Token Flow。`client_id` / `client_secret` / `refresh_token` は DPAPI に保管し、`config.ini` やコードには書かない
- 401 を受けたときだけ再取得して 1 回再試行する（期限は予測しない）
- Client Credentials Flow は本番で使わない（漏えい時に `client_secret` 2 値だけでアクセストークンを取得できるため）。ECA 側でも無効にする
- 実行専用ユーザーを用意し、権限はそのユーザー側で最小限にする
- Refresh Token Rotation を有効にすると comken が新しい token を DPAPI へ **自動で書き戻す** ので運用が増えない

レポート取得は `comken/services/salesforce_downloader` に集約し、**何を取るかは管理表（Excel）に、いつ何を取ったかは履歴（CSV）** に集める。0 件がありえるかどうかは管理表の `0件あり` 列で宣言させる（履歴の回数から自動判定しない）。履歴に「原因区分」を持たせ、`設定` / `Salesforce` / `データなし` / `ファイル` / `プログラム` の 5 値で運用者が履歴だけから一次対応者（管理表を直す人・Salesforce 管理者へ連絡する人）を判断できる。例外クラス名との対応表は持たず、**例外の型だけから**機械的に判定する。

詳細は [`salesforce.md`](salesforce.md) ・ [`salesforce-downloader.md`](salesforce-downloader.md) ・ [`master-table.md`](master-table.md) を参照。

### ブラウザ

- 入口は **`Browsers`** に集約し、サイトが 1 つでも複数でも書き方を変えない
- **サイトごとに 1 ブラウザを起動** し、タブでは分けない（ダウンロード先・ログイン状態がブラウザ単位で決まるため、タブで複数サイトを扱うと取り違え事故が構造的に避けられない）
- **`with` を必須** にする。`with` なしで起動できると、途中で例外が出たときに Edge のプロセスが残り、次の実行でドライバーの更新まで妨げる
- 同期が基本。`start` / `wait` を書いたところだけ非同期にする（重画面の読み込み中に別サイトを進めたい場合）。`parallel` はこの 2 つを並べた短縮形
- 設定は `config.ini` ではなく **クラス変数**（`BrowserOptions` の `DRIVER_PATH` / `WAIT_SECONDS` 等）。プロジェクト固有ではなく環境共通のデフォルトで、差はサブクラスで上書きする

サイト／組織クラス（`SiteBase` / `SalesforceBase` のサブクラス）には **`OWNER = "プロジェクト名 / 担当者"` を必須** とし、未設定だと `SiteOwnerRequiredError` で止める。ライブラリ側で昇格された `comken.toolbox.browser.sites` / `comken.toolbox.salesforce.sites` 配下のクラスは `OWNER = "comken"` を書いて検査を免除する。

詳細は [`browser.md`](browser.md) を参照。

## 8. ブラウザ内部設計

ブラウザ機能を保守するときの参照地図。

### 公開 API

利用プロジェクトは内部ファイルを直接 import せず、次の入口だけを使う。

```python
from comken.toolbox.browser import BrowserOptions, Browsers, Locator, Page
```

`Browsers` / `BrowserSession` などの公開名は互換性のため維持する。内部ファイルは役割が伝わる短い名詞にし、ディレクトリ名と意味が重複する複合ファイル名は避ける。

### ディレクトリ構成

```
browser/
├── __init__.py                 公開 API の入口
├── site.py                     SiteBase（サイトを書く人が最初に読む土台クラス）
├── sites/                      ライブラリ公認サイトの置き場
├── options.py                  Edge の起動設定
├── management/                 ブラウザーと非同期処理の管理
│   ├── browsers.py             複数ブラウザーをまとめて起動・終了する
│   ├── sessions.py             1 サイト分の WebDriver と排他制御
│   ├── startup.py              Edge の起動・初期化
│   ├── tasks.py                裏で動かした処理の結果・例外を受け取る
│   └── tabs.py                 1 セッション内のタブを開閉する
├── page.py                     Page Object の共通操作
├── locator.py                  画面要素の指定方法
└── download.py                 ダウンロード先と完了待ち
```

### 変更先の判断

| 変更したいこと | 主に読むファイル |
|---|---|
| ブラウザーを追加・終了する流れ | `management/browsers.py` |
| Edge の起動・終了、同時操作の防止 | `management/sessions.py` |
| Edge 起動失敗、起動引数 | `management/startup.py` |
| 複数サイトの並列処理 | `management/browsers.py`、`management/tasks.py` |
| ポップアップ、複数タブ読み込み | `management/tabs.py` |
| クリック、入力、待機 | `page.py` |
| Edge の起動引数 | `options.py` |
| ダウンロード完了の判定 | `download.py` |

`BrowserSession` へ新しい責務を直接足す前に、上表の既存担当に置けないか確認する。公開 API を変える場合は、ブラウザ操作文書・サンプル・自動生成 API も同時に更新する。

## 9. 動作環境

| 項目 | 内容 |
|---|---|
| Python | 3.13 以上（`requires-python = ">=3.13"`）。実行環境は 3.14、CI は 3.13 |
| OS | Windows（`toolbox.windows` / `toolbox.browser` は Windows 専用） |
| 必須依存 | openpyxl, selenium, pywin32, requests |
| Outlook 操作 | 従来版（Classic）Outlook が必要。New Outlook は非対応 |
| 参照方法 | 共有サーバーに置き、各プロジェクトの bat が `PYTHONPATH` を設定して直接参照（[`HISTORY.md`](HISTORY.md) §11 を参照） |

## 10. パッケージ構成と配置・運用

### パッケージ構成

- **ライブラリのコードは `src/` レイアウトにしない**（リポジトリ直下に `comken/` を置く）。各 PC が共有サーバーのリポジトリルートを `PYTHONPATH` で参照するため、`comken/` が直下にある構成を前提にする
- 小規模な公開定数は `comken/constants.py` にまとめ、何にも依存しない最下層とする
- 機能パッケージ同士は **原則独立** にする。下から上にだけ向け、toolbox は core・直下・同層に依存してよい。例外的な依存（`excel` → `windows` の COM フォールバック等）は遅延 import にして、片方が入っていない環境でも単体で動くようにする

### 配置時に書き換える3ファイル

リポジトリは公開しているため、社内の名前・URL・共有フォルダのパスは仮名にしてある。配置するとき、次の 3 か所を実際の値へ書き換える。

- `comken/toolbox/salesforce/sites/solution.py` — 本番組織の My Domain・認証情報の接頭辞
- `comken/toolbox/salesforce/sites/solution_sandbox.py` — サンドボックス組織の同
- `comken/services/salesforce_downloader/paths.py` — レポート管理表・履歴を置く共有フォルダ

値の置き場所は **「値を使う場所」**（クラス定義の隣）に閉じる（`settings.ini` / `settings.py` へは集約しない。理由は [`HISTORY.md`](HISTORY.md) §14）。書き換え忘れは必ず組織接続エラー・フォルダ未発見エラーになるので、仮名のまま黙って動いて間違った結果を出すことはない。

共有サーバーではこの 3 ファイルを **`git update-index --skip-worktree`** で切り替えから守る（配置時に 1 回だけ）。タグ切り替え時にこのファイルに変更が入っていると checkout が止まるので、そのときだけ `--no-skip-worktree` で解除し手で合わせる。

### 参照方式: 共有サーバーを直接参照

comken は共有サーバー上の 1 か所に置き、各プロジェクトはそこから **直接 import する**（ローカルへのコピー・同期・`pip install` を行わない）。

共有サーバーのチェックアウトは **リリース済みのタグだけ** に保つ。共有サーバーでブランチをチェックアウトしないこと（その瞬間に全プロジェクトへ伝播するため）。タグだけを指していれば、`master` に何をコミットしても本番へ流れない。

直接参照方式は「配布作業ゼロ・常に最新」が利点。代償は「**共有サーバーが落ちると import が失敗して全プロジェクトが止まる**」ことで、これを受け入れた上での方式。

`sys.pycache_prefix` を `%LOCALAPPDATA%\comken-pycache` へ向ける処理は `comken/__init__.py` が担い、設定作業無しで `__pycache__` がローカルへ書かれる。

## 11. 開発とリリース

### 開発中（毎日）

1. 手元のクローンで `master` にコミットする
2. `python -m pytest -q` ・ `python -m ruff check .` ・ `python -m ruff format --check .` を通す
3. 公開 API・例外を変える変更の後には `python tools\export_for_chat.py` で [`自動生成/API.md`](自動生成/API.md) と [`ERRORS.md`](ERRORS.md) を再生成する
4. push する

実プロジェクトで開発版を試したいときは、そのコマンドプロンプト限りで `PYTHONPATH` を手元のクローンに切り替える。`setx` でユーザー環境変数を書き換えない（戻し忘れると PC が永久に開発版で動き続ける）。

### リリース時

1. `comken/__init__.py` の `__version__` を 1 行変更（**定義はここだけ**）
2. 上のテスト・lint を回す
3. `python tools\export_for_chat.py` で [`自動生成/API.md`](自動生成/API.md) と [`ERRORS.md`](ERRORS.md) を再生成する
4. コミットしてタグを打ち、push（`git tag vX.Y.Z && git push --tags`）
5. 共有サーバーで `git fetch --tags && git checkout vX.Y.Z` を実行する

5 を実行するまで本番は変わらない。1〜4 は好きなときにやってよい。

### SemVer

バージョンの定義は `comken/__init__.py` の `__version__` の 1 か所だけ。

| 桁 | 上げる場面 | 例 |
|---|---|---|
| Z（PATCH） | バグ修正のみ | 0.11.3 → 0.11.4 |
| Y（MINOR） | 機能追加（既存コードはそのまま動く） | 0.11.3 → 0.12.0 |
| X（MAJOR） | 互換性が壊れる変更（原則やらない） | — |

**MAJOR が 0 の間は機能追加でも MINOR を必ず上げる**（API が安定していない前提のため）。

判断に迷ったら **MINOR を上げて**、互換性ポリシーに従って旧名を残すと安全。「後方互換か」を疑ったら、互換ではない。

### v1.0.0 以降の互換性ポリシー

全プロジェクトが常に最新を参照する＝ **古い comken に固定して逃げる手段がない**。そのため公開 API の互換性は次のルールで守る。

| ルール | 内容 |
|---|---|
| 原則、名前は変えない | 公開 API（クラス名・メソッド名・引数名）の変更は最後の手段 |
| 変える場合、旧名は削除しない | 旧名は動き続ける。黙って壊すことはしない |
| 旧名には警告を付ける | 旧 import パス側に `__getattr__` シムを置き、属性を取り出した瞬間に `FutureWarning` を出す |

`FutureWarning` を使う（`DeprecationWarning` はデフォルト非表示で気づけない）。文言は「動作しますが、○○に書き換えてください」とし、Python の警告機構により **同じ箇所からは 1 回の実行につき 1 度しか表示されない** のでスパムにはならない。警告を出し続ける期間は実質無期限（全プロジェクトの grep で旧名の不使用を確認できたら、旧名と警告を削除してよい）。

BO と intranet でバージョンを分けることはしない（版を分けても「どちらが最新か」の問題は解決しない）。環境ごとの差は、同じタグを使ったうえで各環境が使える機能・依存の範囲で扱う。

ロールバックは共有サーバーで前のタグに戻すだけ。次に import した時点で全プロジェクトが戻る。

## 12. 関連ドキュメント

- [`HISTORY.md`](HISTORY.md): 設計判断の **経緯・却下した代替案・理由** だけを集めた文書。現状の説明はここに書かない
- [`CONVENTIONS.md`](../CONVENTIONS.md): **コーディング規約**（1〜14 章は利用者向け、15 章以降は comken 本体の編集者向け）
- [`自動生成/API.md`](自動生成/API.md): 公開 API の署名・docstring（**生成物**、手で編集しない）
- [`ERRORS.md`](ERRORS.md): 例外クラスと非エンジニア向けの対処（**生成物**、手で編集しない）
- [`README.md`](../README.md): 入口とモジュール一覧
