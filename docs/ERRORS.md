# エラー対応ガイド

エラーが出たら、**黒い画面（コンソール）の一番下あたりに出ている「エラー名」**をこの表から探してください。
エラー名は `SheetNotFoundError` のような英語の単語です。

エラー名の表は comken のコードから自動生成しています。表を直すときは例外クラスの
docstring を直してください。手で書き足すのは「まず試すこと」とプロジェクト固有の欄です。

> このファイルは comken の雛形です。プロジェクトで使うときはルートにコピーし、
> そのプロジェクト固有のエラーと対処を追記してください。

---

## まず試すこと（どのエラーでも共通）

1. 開いている Excel ファイルをすべて閉じて、もう一度実行する
2. それでもダメなら、このガイドでエラー名を探す
3. 表にない・解決しない場合は、**エラーの画面全体をスクリーンショット**して管理者に送る

---

## プロジェクト固有のエラー

（プロジェクトごとにここへ追記する）

| エラー名・症状 | 意味 | 対処 |
|---|---|---|
| | | |

---

## それでも解決しないとき

以下をセットで管理者に送ってください。

1. エラー画面全体のスクリーンショット（黒い画面の文字が読める状態で）
2. 何をしようとしていたか（例: 「朝の売上レポート作成を実行した」）
3. いつから起きているか（例: 「昨日までは動いていた」）

---

<!-- ここから下は python export_for_chat.py が自動生成する。手で編集しない -->

## Excel のエラー

| エラー名 | 意味 | 自分でできる対処 |
|---|---|---|
| `ExcelError` | Excel に関するエラー。具体的な状況はメッセージに出る | メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ |
| `ExcelApplicationNotAvailableError` | Excel を起動できない | この PC に Excel が入っているか確認する。入れられない PC で動かすなら、数式ではなく値で書いてもらう（管理表なら、数式の結果を貼り付けてもらう） |
| `SheetNotFoundError` | 指定した名前のシートがない | Excel を開いて、下のシート名（タブ）が変わっていないか確認する。変えた場合は元に戻す |

## Access のエラー

| エラー名 | 意味 | 自分でできる対処 |
|---|---|---|
| `AccessError` | Access に関するエラー | メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ |
| `AccessBackupError` | 元 DB を開く前のバックアップに失敗した | 保存先の空き容量・書き込み権限・元 DB の読み取り権限を確認する |
| `AccessLocalCopyError` | Access ファイルを一時フォルダへコピーできない | 使用状況・読み取り権限・空き容量を確認する |
| `AccessRoutineError` | Access マクロまたは VBA の実行に失敗した | 表示された名前と Access 側の内容を確認する |
| `AccessSourceNotFoundError` | テーブルまたはクエリが見つからない | エラーに表示された存在する名前を確認する |
| `PermissionError` | ファイルが誰かに開かれている | 自分や他の人がそのファイルを開いていないか確認して閉じる |

## Outlook のエラー

| エラー名 | 意味 | 自分でできる対処 |
|---|---|---|
| `OutlookError` | Outlook 関連エラーの分類 | メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ |
| `ClassicOutlookNotAvailableError` | Classic Outlook を利用できない | Classic Outlook を使うか管理者に相談する |
| `OutlookFolderNotFoundError` | 指定したフォルダがない | エラーに表示された存在するフォルダ名を確認する |

## ファイル・設定などのエラー

| エラー名 | 意味 | 自分でできる対処 |
|---|---|---|
| `SiteOwnerRequiredError` | `SiteBase` / `SalesforceBase` のサブクラスに `OWNER` が設定されていない | サブクラスに `OWNER = "プロジェクト名 / 担当者"` を1行追加する。ライブラリ（`comken.toolbox.browser.sites/` または`comken.toolbox.salesforce.sites/`）に入れるべきサイトかは`docs/CONVENTIONS.md` の「サイト／組織クラスを昇格させる基準」を参照して判断する。ライブラリに昇格したい場合はライブラリ管理者へ連絡する。 |
| `CSVError` | CSV に関するエラー。具体的な状況はメッセージに出る | メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ |
| `ColumnNotFoundError` | Excel・CSV・データ比較で列が見つからないエラー。具体的な状況はメッセージに出る | メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ |
| `ExcelColumnNotFoundError` | Excel の列見出しが見つからない | Excel の1行目を確認する |
| `TransferSourceColumnNotFoundError` | 列名転記で、lookup の転記元列が見つからない | 転記元データと config.ini のマッピング左側を確認する |
| `InvalidColumnError` | 列の指定が正しくない（打ち間違いなど） | 列は番号（1, 2, …）か列記号（"A", "AA"）で指定する |
| `ConfigError` | config.ini に関するエラー | メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ |
| `ConfigCreatedFromExampleError` | config.ini が無かったので example から作った | 作られた config.ini の値を書き換えて、もう一度実行する |
| `ConfigLowerCaseNameError` | config.ini のセクション名・キー名に小文字がある | 表示された名前を大文字に書き換える（`[files]` → `[FILES]`） |
| `ConfigSectionNotFoundError` | config.ini の必要な節がない | メッセージに表示された **「読んだファイル」のパス** が、編集しているconfig.ini と一致するかを確認する（2026-08-18 にプロジェクトの場所を基準にするように変えてから、起動方法によって別の config.ini を読むことがあるため）。パスが正しければ、表示されたセクション名をconfig.ini に追加する。**見た目では原因が分からない場合**（行頭に空白が混入していた等）はエディタで行頭空白・全角スペースを確認する |
| `ConfigKeyNotFoundError` | config.ini のセクションに必要なキーがない | メッセージに表示された **「読んだファイル」のパス** が、編集しているconfig.ini と一致するかを確認する。パスが正しければ、表示されたキー名を該当セクションへ追加する。**セクション名は合っているがキー名を 1 文字タイポした** とき（FILES.OUTPUT_FOLER 等）は、「もしかして」に近いキー名が出るので、それを config.ini に書き直す |
| `ConfigMappingEmptyValueError` | ``[*_MAPPING]`` セクションの値が空欄 | メッセージに表示された **「読んだファイル」のパス** が、編集しているconfig.ini と一致するかを確認する。パスが正しければ、表示されたキー名の両側に値を書いて config.ini を直す（``列名 = 値``）。``=`` を付け忘れて ``キー`` のように書いた行もここで検出する（``cfg.get()`` が ``None`` を返すので空欄と同じ扱い）。通常セクションの空欄（``READ_PASSWORD =`` のように「設定しない」を示す書き方）はエラーにしないので、``*_MAPPING`` 以外では無視してよい |
| `ConfigSubclassingNotSupportedError` | ``Config`` を継承できない | ``from comken import config`` で ``config.SECTION.KEY`` を直接読む。サブクラスでメソッドを足しても ``Config.__new__`` がパス単位でキャッシュ済みの素の ``Config`` を返すため、 追加したメソッドは``AttributeError`` になる（キャッシュを ``cls`` 対応にする改修は行わない）。 |
| `ComkenFileNotFoundError` | ファイルまたはフォルダが見つからない | エラーに表示されたパスと名前が正しいか、存在するかを確認する |
| `UnsupportedFileSuffixError` | 対応外の拡張子が指定された | CSV / Excel の対応する拡張子のファイルを指定する |
| `FileDeletionError` | ファイルを削除できなかった | 他のプロセスがファイルを掴んでいないか、読み取り専用になっていないかを確認してもう一度実行する。消せたファイルは消えているAttributes:remaining: 削除できなかったファイルのパス一覧。 |
| `FileSuffixMissingError` | ファイル名に拡張子が無い | ファイル名に拡張子（例: ``.csv`` / ``.xlsx``）を含めて指定する。拡張子は名前の文字列にだけ書く。引数 ``ext`` / ``extension`` は廃止済みのため使えない。 |
| `CredentialError` | 認証情報の保存・取得に関するエラー | メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ |
| `InvalidCredentialNameError` | 認証情報のキー名に使えない文字がある | 半角英数字とアンダースコアだけにする（漢字・スペース・記号は使えない） |
| `CredentialNotFoundError` | 認証情報（パスワード・client_secret など）が登録されていない | 表示された登録済みキー名と見比べる。無ければ `python -m comken cred import 認証情報.json` で取り込む |
| `CredentialDecryptionError` | 認証情報を復号できない | 登録したときと**同じ Windows アカウント・同じ PC** で実行しているか確認する。タスクスケジューラの実行ユーザー違いが最も多い |
| `CredentialStoreCorruptedError` | 認証情報の中身が壊れている | 実行アカウントの問題ではない。表示されたファイルを削除して、もう一度取り込み直す |
| `CredentialImportError` | 取り込む JSON が壊れている・形式が違う | 表示された形式のとおりに書き直す。値は必ず `" "` で囲む |
| `PasswordRejectedError` | サイト側が新しいパスワードを拒否した（記号が足りない・文字数が足りない等） | 表示されたエラー内容（サイト側の拒否理由）を確認し、要件を満たすパスワードを入力し直す |
| `SalesforceError` | Salesforce に関するエラー。具体的な状況はメッセージに出る | メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ |
| `SalesforceAuthError` | Salesforce にログインできない | 表示された確認項目を上から順に見る。それでも直らなければ管理者へ連絡する |
| `SalesforceRequestError` | Salesforce が処理を断った | 表示されたメッセージをそのまま添えて管理者へ連絡する（権限か項目名の問題が多い） |
| `SalesforceReportTruncatedError` | レポートが上限の 2000 行で切れた（**全件ではない**） | 期間を狭めて何回かに分けて実行する。1回で全部必要なら管理者へ連絡する |
| `SalesforceReportIDNotFoundError` | レポートの URL からレポート ID を取り出せない | Salesforce でレポートを開いたときのアドレスを、そのまま貼り直す |
| `MasterTableError` | Excel の管理表に関するエラー。具体的な状況はメッセージに出る | メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ |
| `MasterRowValueError` | 管理表の値が正しくない | メッセージに出ている行と列を、管理表で確認して直す |
| `MasterDuplicateValueError` | 一意であるべき列に、同じ値が2つ以上ある | 管理表を開いて、重複している値のどちらかを別の値に変える |
| `StateError` | state.ini に関するエラー | メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ |
| `StateFileCorruptedError` | state.ini が壊れていて読み取れない | 内容を直す。直せない場合は別名に変更して、空の状態から再実行する |
| `StateLowerCaseNameError` | state のキー名に小文字がある | 表示されたキー名を大文字に直す（`last_file` → `LAST_FILE`） |
| `StateValueTypeError` | state に保存できない型の値が渡された | 真偽値・整数・小数・文字列・文字列のリストのいずれかに変更する |
| `BusinessDayNotFoundError` | 営業日が見つからなかった | n をその月の営業日数以下に直す、対象月の祝日に過不足がないか確認する、社内休日（会社用カレンダーCSV）が広範囲に登録されていないか確認する |
| `CalendarError` | 祝日カレンダーに関するエラー | メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ |
| `CalendarFormatError` | 会社用カレンダーCSV 以外のファイルや壊れたファイルを読み込もうとした | ``python -m comken.core.calendar.build`` を実行して``comken/core/calendar/data/company_calendar.csv`` を再生成する。内閣府の ``syukujitsu.csv`` 形式変更が原因の場合は``comken.core.calendar.build`` 側の解析ロジックを直す |
| `DownloaderError` | Salesforce レポートの集約取得に関するエラー | メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ |
| `HistoryWriteError` | 必須のダウンロード履歴を記録できなかった | 履歴CSVの保存先、共有サーバー接続、書込み権限を確認する |
| `HistoryLockTimeoutError` | ダウンロード履歴の排他ロックを待っても取得できなかった | 同時実行中の処理が終わるのを待って再実行する。繰り返す場合は共有サーバーを確認する |
| `CachedReportNotFoundError` | 本日の定期取得キャッシュが見つからない | Salesforce からCSVを手動取得し、画面に表示された正確なパス・ファイル名で置いて、同じ python main.py を再実行する |
| `ReportNotRegisteredError` | 指定した管理番号が管理表に無い | 管理表を開いて、その管理番号の行があるか確認する。新しく使うレポートは、先に管理表へ登録する |
| `SoqlReportNotRegisteredError` | 管理表の「SOQL」列が「○」なのに、同じ管理番号の SoqlReport が登録されていない | 管理番号に対応する ``SoqlReport`` サブクラスを追加し、``KEY`` を管理表と同じ値にして ``soql_reports/_registry.py`` の ``SOQL_REPORTS`` へ登録する。まだ SOQL 化していないなら、管理表の「SOQL」列を「×」に戻す |
| `GroupNotRegisteredError` | 管理表の「グループ」列に設定シートに登録されていない値が書かれている | 管理表の「グループ」列に書かれた値が、設定シート（`group_settings.py` の`GroupSetting`）の「グループ」列に存在するか確認する。新しく部署・グループを追加するときは、設定シート側にも同じ名前で行を足す |
| `EmptyReportError` | レポートは実行できたが明細が 0 行だった | Salesforce の画面で同じレポートを開き、本当に 0 件か確認する。0 件が正常に起こるレポートなら、管理表の「0件あり」を「○」にする。 |
| `ReportFolderNotFoundError` | 保存先として組み立てたフォルダが無い | 設定シートの「ベースURL」（フォルダのパス）と、管理表の「グループ」を確認する。共有フォルダなら、つながっているか・権限があるかも確認する |
| `ReportReservePathLimitError` | 保存ファイル名の連番が上限に達した | 保存先フォルダが想定どおりか確認する。 共有フォルダなら、 古い取得ファイルを退避するか、 別の保存先に変える。 連発する場合は権限・排他制御の設定も見直す |
| `ScheduledDownloadFailedError` | 定期取得で1件以上が失敗した | 履歴（ダウンロード履歴.csv）の「エラー内容」で、失敗した理由を確認する。急いで必要なものは download_scheduled() をスケジュール外で実行する。権限を持つ人が Salesforce から手動でダウンロードしてもよい |
| `LoggingAlreadyConfiguredError` | root logger がすでに設定されている | setup_logging() または setup_local_logging() はアプリの入口で1回だけ呼ぶ。実行基盤がログを設定する場合は呼ばない。 |
| `LoggingConflictError` | root logger に comken 以外の handler が設定されている | 上の handler 一覧をそのままライブラリの管理者へ連絡してください（連絡先は環境ごとに異なるので、ここには書かない）。やむを得ず共存させたい場合は、呼び出し時に ``allow_existing=True``を指定すれば処理は続きますが、comken のハンドラーが追加されることで既存ライブラリのログが**二重**に出たり、出力先が想定と変わる可能性があります。 |
| `LogRootNotConfiguredError` | LoggerSite の LOG_ROOT が設定されていない | サブクラスに ``LOG_ROOT = "\\server\share\logs"`` を1行追加する（絶対パスまたは UNC 文字列。LOG_FOLDER_NAMES のフォルダ名はこの下に作られる）。 |
| `FileNotFoundError` | ファイルが見つからない | ファイルの置き場所と名前を確認する。「今日の日付のファイル」を探す処理なら、今日のファイルが作られているか確認する |

## ブラウザ（Edge 自動操作）のエラー

| エラー名 | 意味 | 自分でできる対処 |
|---|---|---|
| `BrowserError` | ブラウザ操作に関するエラー。具体的な状況はメッセージに出る | メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ |
| `ElementNotFoundError` | 画面の部品が時間内に見つからない | もう一度実行する。サイトが重いだけのことが多い。毎回出るなら画面が変わった可能性があるので管理者へ（エラーに、どの部品を探していたかが出ます） |
| `LoginFailedError` | ログインに失敗した（ユーザー名・パスワードが違う等） | 表示されたエラー内容（サイト側のエラーメッセージ）を確認する。DPAPI に保存した認証情報が古くなっていないか`python -m comken cred list` で確認し、必要なら`python -m comken cred gui` で登録し直す |
| `WebDriverException` | ブラウザ操作の一般的なエラー | Edge のウィンドウをすべて閉じて再実行する |

## Table のエラー

| エラー名 | 意味 | 自分でできる対処 |
|---|---|---|
| `TableError` | 表データの読み書き・転記に関するエラー。具体的な状況はメッセージに出る | 画面に表示された具体的なエラー内容を確認する |
| `InvalidTableInputError` | Table API に対応しない入力が渡された。 | columns、rows、types の型と列名を確認する |
| `TableColumnNotFoundError` | Table に指定された列が存在しない。 | Table.columns を確認し、存在する列名を指定する |
| `TableDuplicateKeyError` | Table の索引または比較に使うキーが重複している。 | キー列の値を一意にしてから処理をやり直す |

## Windows 操作のエラー

| エラー名 | 意味 | 自分でできる対処 |
|---|---|---|
| `WindowNotFoundError` | 指定したウィンドウが見つからない | 対象ウィンドウが開いているか、タイトル（完全一致）が想定どおりかを確認する |

## Data Loader のエラー

| エラー名 | 意味 | 自分でできる対処 |
|---|---|---|
| `DataLoaderError` | Data Loader の実行に関するエラー。具体的な状況はメッセージに出る | メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ |

## すべてのエラーに共通の親

`ComkenError` は、comken が出すエラーすべての親です。画面に表示されたエラー名を
上の表から探してください。

| エラー名 | 意味 | 自分でできる対処 |
|---|---|---|
| `ComkenError` | comken が出す固有エラー全体 | メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ |
