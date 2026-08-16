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
| `ExcelFileNotFoundError` | Excel ファイルが見つからない | ファイルの置き場所と名前を確認する |
| `ExcelApplicationNotAvailableError` | Excel を起動できない | この PC に Excel が入っているか確認する。入れられない PC で動かすなら、数式ではなく値で書いてもらう（管理表なら、数式の結果を貼り付けてもらう） |
| `SheetNotFoundError` | 指定した名前のシートがない | Excel を開いて、下のシート名（タブ）が変わっていないか確認する。変えた場合は元に戻す |
| `SheetAlreadyExistsError` | 同じ名前のシートが既にある | 別のシート名を指定するか、既存のシート名を変更する |
| `LastSheetDeletionError` | ブックの最後のシートを削除しようとした | 先に別のシートを追加してから削除する |
| `InvalidTableNameError` | Excel で使えないテーブル名を指定した | 空白・数字始まり・セル参照のような名前を避ける |
| `TableAlreadyExistsError` | 同じ名前のテーブルが既にある | 別のテーブル名を指定する |
| `TableNotFoundError` | 指定したテーブルがシートにない | エラーに表示された既存テーブル名を確認する |
| `TableNotAvailableInReadOnlyError` | read_only で開いたブックからテーブル名で読めない | ExcelReader を ``tables=True`` で開き直す。例: ``ExcelReader(path, tables=True)`` のように指定する。 |
| `MacroError` | Excel のマクロが失敗した | Excel をすべて閉じて再実行する。続く場合は管理者へ |
| `RowTransferError` | Excel の行転記に失敗した | 表示された行番号のデータを確認する |
| `EmptyHeaderCellError` | Excel の見出しに空欄がある | Excel の1行目の空欄を埋める |
| `ExcelHeadersTooFewError` | 指定した見出し数が列数より少ない | 管理者へ連絡する |
| `FileFormatMismatchError` | 保存拡張子と形式が合わない | 管理者へ連絡する |

## Access のエラー

| エラー名 | 意味 | 自分でできる対処 |
|---|---|---|
| `AccessBackupError` | 元 DB を開く前のバックアップに失敗した | 保存先の空き容量・書き込み権限・元 DB の読み取り権限を確認する |
| `AccessFileNotFoundError` | Access ファイルが見つからない | ファイルの置き場所と名前を確認する |
| `AccessLocalCopyError` | Access ファイルを一時フォルダへコピーできない | 使用状況・読み取り権限・空き容量を確認する |
| `AccessRoutineError` | Access マクロまたは VBA の実行に失敗した | 表示された名前と Access 側の内容を確認する |
| `AccessSourceNotFoundError` | テーブルまたはクエリが見つからない | エラーに表示された存在する名前を確認する |
| `PermissionError` | ファイルが誰かに開かれている | 自分や他の人がそのファイルを開いていないか確認して閉じる |

## Outlook のエラー

| エラー名 | 意味 | 自分でできる対処 |
|---|---|---|
| `OutlookError` | Outlook 関連エラーの分類 | 下の個別エラーを確認する |
| `ClassicOutlookNotAvailableError` | Classic Outlook を利用できない | Classic Outlook を使うか管理者に相談する |
| `OutlookFolderNotFoundError` | 指定したフォルダがない | エラーに表示された存在するフォルダ名を確認する |
| `OutlookAttachmentNotFoundError` | 添付ファイルがない | 表示されたファイルパスを確認する |

## ファイル・設定などのエラー

| エラー名 | 意味 | 自分でできる対処 |
|---|---|---|
| `EncodingDetectionError` | CSV の文字コードを判定できない | CSV の保存形式を確認し、管理者へ連絡する |
| `CsvHeadersTooFewError` | 指定した見出し数が CSV の列数より少ない | 管理者へ連絡する |
| `CsvNoDataRowsError` | CSV に見出し以外のデータ行がない | 見出し行の下にデータが1行以上あるか確認する |
| `CsvRowNotFoundError` | キーに一致する行が CSV に無い | 探している値の書き方（前後の空白・全角半角・ゼロ埋め）を元データと見比べる |
| `CsvRowDuplicateKeyError` | キーにする列に同じ値が複数ある | 表示された値の行を元データで確認し、重複を取り除く。重複が正しいデータなら管理者へ連絡する |
| `CsvCellReferenceError` | CSV のセル位置（例: A2）の指定が正しくない、または範囲外 | 表示されたセル位置と、CSV の行数・列数を確認する |
| `ExcelColumnNotFoundError` | Excel の列見出しが見つからない | Excel の1行目を確認する |
| `CsvColumnNotFoundError` | CSV の列見出しが見つからない | CSV の1行目を確認する |
| `KeyColumnNotFoundError` | 比較に使うキー列が見つからない | Excel・CSV の列名を確認する |
| `TransferKeyColumnNotFoundError` | 列名転記で、Excel のキー列が見つからない | Excel のヘッダー行と key_col の列名を確認する |
| `TransferDestinationColumnNotFoundError` | 列名転記で、Excel の転記先列が見つからない | Excel のヘッダー行と config.ini のマッピング右側を確認する |
| `TransferSourceColumnNotFoundError` | 列名転記で、lookup の転記元列が見つからない | 転記元データと config.ini のマッピング左側を確認する |
| `InvalidColumnError` | 列の指定が正しくない（打ち間違いなど） | 列は番号（1, 2, …）か列記号（"A", "AA"）で指定する |
| `ConfigFileNotFoundError` | config.ini が見つからない | config.ini.example をコピーして config.ini を作る |
| `ConfigCreatedFromExampleError` | config.ini が無かったので example から作った | 作られた config.ini の値を書き換えて、もう一度実行する |
| `ConfigLowerCaseNameError` | config.ini のセクション名・キー名に小文字がある | 表示された名前を大文字に書き換える（`[files]` → `[FILES]`） |
| `ConfigRequiredKeysMissingError` | config.ini に必須の項目がない | エラーに表示された項目を config.ini へ追加する |
| `ConfigSectionNotFoundError` | config.ini の必要な節がない | 表示されたセクション名を config.ini に追加する |
| `UnsupportedFileSuffixError` | 対応外の拡張子が指定された | CSV / Excel の対応する拡張子のファイルを指定する |
| `RpaLibraryNotFoundError` | 社内ライブラリを読み込めない | 実行.bat の PYTHONPATH に社内ライブラリが入っているか確認する。バージョンが変わった場合は管理者へ連絡する |
| `InvalidCredentialNameError` | 認証情報のキー名に使えない文字がある | 半角英数字とアンダースコアだけにする（漢字・スペース・記号は使えない） |
| `CredentialNotFoundError` | 認証情報（パスワード・client_secret など）が登録されていない | 表示された登録済みキー名と見比べる。無ければ `python -m comken.toolbox.credentials import 認証情報.json` で取り込む |
| `CredentialDecryptionError` | 認証情報を復号できない | 登録したときと**同じ Windows アカウント・同じ PC** で実行しているか確認する。タスクスケジューラの実行ユーザー違いが最も多い |
| `CredentialStoreCorruptedError` | 認証情報の中身が壊れている | 実行アカウントの問題ではない。表示されたファイルを削除して、もう一度取り込み直す |
| `CredentialImportError` | 取り込む JSON が壊れている・形式が違う | 表示された形式のとおりに書き直す。値は必ず `" "` で囲む |
| `SalesforceAuthError` | Salesforce にログインできない | 表示された確認項目を上から順に見る。それでも直らなければ管理者へ連絡する |
| `SalesforceConnectionError` | Salesforce につながらない | ネットワークの状態を確認して、少し待ってから再実行する |
| `SalesforceRequestError` | Salesforce が処理を断った | 表示されたメッセージをそのまま添えて管理者へ連絡する（権限か項目名の問題が多い） |
| `SalesforceExternalIdMissingError` | upsert 用データに外部 ID がない | 管理者へ連絡する |
| `SalesforceCredentialRotationError` | consumer key / secret のローテーションを安全に完了できない | Salesforce の ECA 設定・API レスポンス・DPAPI の保存先を確認する |
| `SalesforceReportTruncatedError` | レポートが上限の 2000 行で切れた（**全件ではない**） | 期間を狭めて何回かに分けて実行する。1回で全部必要なら管理者へ連絡する |
| `SalesforceReportFormatError` | レポートの形式が対応していない | レポートを明細形式にするか、管理者へ連絡する |
| `SalesforceReportIdNotFoundError` | レポートの URL からレポート ID を取り出せない | Salesforce でレポートを開いたときのアドレスを、そのまま貼り直す |
| `SalesforceReportExecutionError` | Salesforce 側でレポート実行に失敗した | Salesforce で同じレポートを直接実行し、表示された内容を管理者へ連絡する |
| `SalesforceSiteNotFoundError` | URL のドメインに対応する組織が登録されていない | URL のドメインを見直す。新しい組織なら管理者へ連絡する（組織クラスの追加が要る） |
| `MasterTableError` | Excel の管理表に関するエラー | 画面に表示された具体的なエラー名を上の表から探す |
| `MasterSheetNotDefinedError` | 管理表の場所が決まっていない | `load(パス)` のようにファイルを渡すか、クラスに PATH を書く（コードの直し方の話なので、非エンジニアが見た場合は管理者へ連絡する） |
| `MasterColumnNotFoundError` | 管理表に必要な列（見出し）が無い | 管理表の1行目（見出し）を元に戻す。消してしまった場合は、メッセージに出ている「今ある見出し」と見比べて足す |
| `MasterRowValueError` | 管理表の値が正しくない | メッセージに出ている行と列を、管理表で確認して直す |
| `MasterDuplicateValueError` | 一意であるべき列に、同じ値が2つ以上ある | 管理表を開いて、重複している値のどちらかを別の値に変える |
| `StateFileCorruptedError` | state.ini が壊れていて読み取れない | 内容を直す。直せない場合は別名に変更して、空の状態から再実行する |
| `StateLowerCaseNameError` | state のキー名に小文字がある | 表示されたキー名を大文字に直す（`last_file` → `LAST_FILE`） |
| `StateValueTypeError` | state に保存できない型の値が渡された | 真偽値・整数・小数・文字列・文字列のリストのいずれかに変更する |
| `ReportNotRegisteredError` | 指定した管理番号が管理表に無い | 管理表を開いて、その管理番号の行があるか確認する。新しく使うレポートは、先に管理表へ登録する |
| `ReportDisabledError` | 管理表で「無効」になっているレポートを取ろうとした | また使うなら管理表の「有効」を「有効」に戻す。使わないなら、呼び出し側のコードから消す |
| `InvalidReportUrlError` | 管理表の URL から Salesforce のレポート ID を取り出せない | Salesforce でレポートを開いたときのアドレスを、そのまま貼り直す |
| `ScheduledReportNotRegisteredError` | 定期取得の対象として登録されていないレポートを、定期取得済みとして受け取ろうとした | 毎日決まった時刻に取るなら、管理表の「実行方式」を「定期」にする。使うときに毎回取りに行くなら、download_report() を呼ぶ |
| `ScheduledReportNotDownloadedError` | 本日の定期取得がまだ済んでいない | 定期取得の実行結果を確認する。急ぐ場合は download_report() でその場で取得する（そのぶん Salesforce への呼び出しが増える） |
| `ReportFileMissingError` | 履歴では取得済みだが、保存先にファイルが無い | 保存先のフォルダを確認する。消してしまった場合はdownload_report() で取り直す |
| `EmptyReportError` | レポートは実行できたが明細が 0 行だった | Salesforce の画面で同じレポートを開き、本当に 0 件か確認する。本当に 0 件の日であれば、空の CSV を保存先へ手で置く |
| `ReportFolderNotFoundError` | 管理表に書かれた保存先のフォルダが無い | 管理表の「保存先」を確認する。共有フォルダなら、つながっているか・権限があるかも確認する |
| `ScheduledDownloadFailedError` | 定期取得で1件以上が失敗した | 履歴（ダウンロード履歴.csv）の「エラー内容」で、失敗した理由を確認する。急いで必要なものは download_report() でその場で取得する |
| `FileNotFoundError` | ファイルが見つからない | ファイルの置き場所と名前を確認する。「今日の日付のファイル」を探す処理なら、今日のファイルが作られているか確認する |

## ブラウザ（Edge 自動操作）のエラー

| エラー名 | 意味 | 自分でできる対処 |
|---|---|---|
| `DriverStartError` | ブラウザを起動できない | エラーの本文にある確認事項をそのまま試す。Windows Update で Edge が更新された直後に起きやすい |
| `BrowsersNotStartedError` | `with` を使わずに `Browsers` を使った | `with Browsers() as browsers:` の中で使う（ブラウザは起動していないので実害はない） |
| `BrowsersClosedError` | `with` を抜けた後の `Browsers` を使った | 続けたい処理を `with` の中に入れる。外へ持ち出すのは取り出した値だけにする |
| `SessionNotStartedError` | `with` を使わずにブラウザを操作した | `with Browsers() as browsers:` の中で使う |
| `SessionClosedError` | `with` を抜けた後のブラウザを操作した | `with` の外へ持ち出すのは、ブラウザではなく取り出した値にする |
| `ConcurrentSessionUseError` | 1つのブラウザを複数の処理から同時に操作した | サイトごとに `launch` でブラウザを分ける |
| `SessionNameConflictError` | 同じ名前で2回 `launch` した | 名前を変える（同一サイトの別アカウントなら `kintai_a` / `kintai_b` など） |
| `SessionNotFoundError` | `launch` していない名前を取り出した | 先に `launch` する。エラーに起動済みの一覧が出ます |
| `SiteConfigError` | `SiteBase` サブクラスの設定が不足している | サブクラスに NAME を定義する（BASE_URL / OPTIONS も同じ） |
| `SiteNotStartedError` | まだ起動していないサイトの画面を作ろうとした | `with Kintai() as kintai:` の中で使う |
| `ElementNotFoundError` | 画面の部品が時間内に見つからない | もう一度実行する。サイトが重いだけのことが多い。毎回出るなら画面が変わった可能性があるので管理者へ（エラーに、どの部品を探していたかが出ます） |
| `PopupTabNotOpenedError` | 別タブが開かない | もう一度実行する。続く場合は、その画面の「別ウィンドウで開く」ボタンが変わった可能性があるので管理者へ |
| `DownloadTimeoutError` | ダウンロードが終わらない | ネットワークの状態を確認して再実行する。大きいファイルなら時間がかかっているだけのこともある |
| `WebDriverException` | ブラウザ操作の一般的なエラー | Edge のウィンドウをすべて閉じて再実行する |

## 分類（まとめて捕捉する用）

次の名前は、似たエラーをプログラム側でまとめて扱うための分類です。
これらの名前が単独で表示されることはありません。対処するときは、画面に表示された
具体的なエラー名を上の表から探してください。

| エラー名 | 意味 | 自分でできる対処 |
|---|---|---|
| `ComkenError` | comken が出す固有エラー全体 | 画面に表示された具体的なエラー名を上の表から探す |
| `ExcelError` | Excel に関するエラー | 画面に表示された具体的なエラー名を上の表から探す |
| `AccessError` | Access に関するエラー | 画面に表示された具体的なエラー名を上の表から探す |
| `CsvError` | CSV に関するエラー | 画面に表示された具体的なエラー名を上の表から探す |
| `ColumnNotFoundError` | Excel・CSV・データ比較で列が見つからないエラー | 画面に表示された具体的なエラー名を上の表から探す |
| `ConfigError` | config.ini に関するエラー | 画面に表示された具体的なエラー名を上の表から探す |
| `StateError` | state.ini に関するエラー | 画面に表示された具体的なエラー名を上の表から探す |
| `DownloaderError` | Salesforce レポートの集約取得に関するエラー | 画面に表示された具体的なエラー名を上の表から探す |
| `RpaError` | 社内 RPA 基盤の呼び出しに関するエラー | 画面に表示された具体的なエラー名を上の表から探す |
| `SalesforceError` | Salesforce に関するエラー | 画面に表示された具体的なエラー名を上の表から探す |
| `CredentialError` | 認証情報の保存・取得に関するエラー | 画面に表示された具体的なエラー名を上の表から探す |
| `BrowserError` | ブラウザ操作に関するエラー | 画面に表示された具体的なエラー名を上の表から探す |
