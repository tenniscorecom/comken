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
| `DataSheetAccessError` | データシートと表示用シートの責務に反する操作をした。 | data_ で始まるシートは table()、それ以外はセル・範囲 API で操作する |
| `ExcelFileNotFoundError` | Excel ファイルが見つからない | ファイルの置き場所と名前を確認する |
| `ExcelApplicationNotAvailableError` | Excel を起動できない | この PC に Excel が入っているか確認する。入れられない PC で動かすなら、数式ではなく値で書いてもらう（管理表なら、数式の結果を貼り付けてもらう） |
| `SheetNotFoundError` | 指定した名前のシートがない | Excel を開いて、下のシート名（タブ）が変わっていないか確認する。変えた場合は元に戻す |
| `SheetAlreadyExistsError` | 同じ名前のシートが既にある | 別のシート名を指定するか、既存のシート名を変更する |
| `SheetNameError` | 表示用シートに使えない名前を ``create_sheet`` に渡した | 予約接頭辞 ``PY_`` を除いた名前を ``create_sheet`` に渡すか、データシートとして作る場合は ``create_data_sheet`` を使う |
| `InvalidTableNameError` | Excel で使えないテーブル名を指定した | 空白・数字始まり・セル参照のような名前を避ける |
| `TableAlreadyExistsError` | 同じ名前のテーブルが既にある | 別のテーブル名を指定する |
| `TableFormulaOverwriteError` | テーブル内の人が入れた数式を値で潰そうとした | 数式を保持したい場合は、``replace()`` のあとに該当セルへ元の数式を書き戻す。意図的に値で潰してよいときだけ ``allow_formula_overwrite=True`` を渡す |
| `TableColumnMismatchError` | 渡された Table の列が既存テーブルの見出しと一致しない | 既存の見出しと一致するように渡す Table の列を修正する。数式で参照される列は渡さない（「金額」のように計算で決まる列をTable に含めない、または数式を保持する前提の列として残す） |
| `TableNotFoundError` | 指定したテーブルがシートにない | エラーに表示された既存テーブル名を確認する |
| `MacroError` | Excel のマクロが失敗した | Excel をすべて閉じて再実行する。続く場合は管理者へ |
| `EmptyHeaderCellError` | Excel の見出しに空欄がある | Excel の1行目の空欄を埋める |
| `DuplicateHeaderCellError` | Excel の見出し名が重複している | Excel の見出し名を重複しない名前に変更する |
| `EmptyExcelTableError` | Excel テーブル定義はあるが、定義範囲を1行も読み取れない。 | Excel のテーブル定義範囲を確認する |
| `ExcelHeadersTooFewError` | 指定した見出し数が列数より少ない | 管理者へ連絡する |
| `ExcelMacroPreservationError` | 保存予定のブックからVBAプロジェクトが欠落または変化した。 | 元ファイルは保持される。管理者に連絡し、Excel実機で保存方法を確認する |
| `ExcelReadOnlyOperationError` | read_only=True の Excel に書き込もうとした。 | read_only=False で開き直すか、書き込みが要らない操作かを見直す（読み取りだけなら Excel(path, read_only=True) で十分） |
| `ExcelSaveValidationError` | 保存予定のExcelファイルを再度開けず、安全に置き換えられない。 | 元ファイルは保持される。空き容量とExcel形式を確認して再実行する |
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
| `SiteOwnerRequiredError` | `SiteBase` / `SalesforceBase` のサブクラスに `OWNER` が設定されていない | サブクラスに `OWNER = "プロジェクト名 / 担当者"` を1行追加する。ライブラリ（`comken.toolbox.browser.sites/` または`comken.toolbox.salesforce.sites/`）に入れるべきサイトかは`docs/開発/ライブラリ開発規約.md` の「サイト／組織クラスを昇格させる基準」を参照して判断する。ライブラリに昇格したい場合はライブラリ管理者へ連絡する。 |
| `InternalLibraryNotFoundError` | 指定した社内ライブラリが見つからない | 社内 LAN 環境から、共有サーバ上の PYTHONPATH が通っているか確認し、指定したライブラリ名のフォルダが存在するか確かめる |
| `InternalLibraryVersionMismatchError` | 指定したバージョンの社内ライブラリが見つからない | 共有サーバ上の対象ライブラリのバージョンを確認し、呼び出し側の指定と一致しているか確かめる |
| `EncodingDetectionError` | CSV の文字コードを判定できない | CSV の保存形式を確認し、管理者へ連絡する |
| `CSVFileNotFoundError` | 読み込む CSV ファイルが存在しない | パスを確認する。新規出力は columns を指定して write / replace する |
| `CSVHeaderMissingError` | CSV に見出し行がない | 見出し行を追加するか、ヘッダーなし CSV なら columns を指定する |
| `CSVInvalidHeaderError` | CSV の見出しに空欄または重複がある | CSV の1行目にある空欄または重複した見出しを直す |
| `CSVRowLengthError` | CSV のデータ行の列数が見出し数と一致しない | 表示された行の区切り文字と値の数を確認する |
| `CSVColumnsRequiredError` | 空の新規 CSV に出力する列を決定できない | CSV(columns=[...]) または Table(columns, []) で列を指定する |
| `ExcelColumnNotFoundError` | Excel の列見出しが見つからない | Excel の1行目を確認する |
| `KeyColumnNotFoundError` | 比較に使うキー列が見つからない | Excel・CSV の列名を確認する |
| `TransferSourceColumnNotFoundError` | 列名転記で、lookup の転記元列が見つからない | 転記元データと config.ini のマッピング左側を確認する |
| `InvalidColumnError` | 列の指定が正しくない（打ち間違いなど） | 列は番号（1, 2, …）か列記号（"A", "AA"）で指定する |
| `ConfigFileNotFoundError` | config.ini が見つからない | config.ini.example が同じ場所にあるか確認する（あれば実行し直すだけで作られる） |
| `ConfigCreatedFromExampleError` | config.ini が無かったので example から作った | 作られた config.ini の値を書き換えて、もう一度実行する |
| `ConfigLowerCaseNameError` | config.ini のセクション名・キー名に小文字がある | 表示された名前を大文字に書き換える（`[files]` → `[FILES]`） |
| `ConfigSectionNotFoundError` | config.ini の必要な節がない | メッセージに表示された **「読んだファイル」のパス** が、編集しているconfig.ini と一致するかを確認する（2026-08-18 にプロジェクトの場所を基準にするように変えてから、起動方法によって別の config.ini を読むことがあるため）。パスが正しければ、表示されたセクション名をconfig.ini に追加する。**見た目では原因が分からない場合**（行頭に空白が混入していた等）はエディタで行頭空白・全角スペースを確認する |
| `ConfigKeyNotFoundError` | config.ini のセクションに必要なキーがない | メッセージに表示された **「読んだファイル」のパス** が、編集しているconfig.ini と一致するかを確認する。パスが正しければ、表示されたキー名を該当セクションへ追加する。**セクション名は合っているがキー名を 1 文字タイポした** とき（FILES.OUTPUT_FOLER 等）は、「もしかして」に近いキー名が出るので、それを config.ini に書き直す |
| `ConfigMappingEmptyValueError` | ``[*_MAPPING]`` セクションの値が空欄 | メッセージに表示された **「読んだファイル」のパス** が、編集しているconfig.ini と一致するかを確認する。パスが正しければ、表示されたキー名の両側に値を書いて config.ini を直す（``列名 = 値``）。``=`` を付け忘れて ``キー`` のように書いた行もここで検出する（``cfg.get()`` が ``None`` を返すので空欄と同じ扱い）。通常セクションの空欄（``READ_PASSWORD =`` のように「設定しない」を示す書き方）はエラーにしないので、``*_MAPPING`` 以外では無視してよい |
| `ConfigSubclassingNotSupportedError` | ``Config`` を継承できない | ``from comken import config`` で ``config.SECTION.KEY`` を直接読む。サブクラスでメソッドを足しても ``Config.__new__`` がパス単位でキャッシュ済みの素の ``Config`` を返すため、 追加したメソッドは``AttributeError`` になる（キャッシュを ``cls`` 対応にする改修は行わない）。 |
| `UnsupportedFileSuffixError` | 対応外の拡張子が指定された | CSV / Excel の対応する拡張子のファイルを指定する |
| `FileDeletionError` | ファイルを削除できなかった | 他のプロセスがファイルを掴んでいないか、読み取り専用になっていないかを確認してもう一度実行する。消せたファイルは消えているAttributes:remaining: 削除できなかったファイルのパス一覧。 |
| `FileSuffixMissingError` | ファイル名に拡張子が無い | ファイル名に拡張子（例: ``.csv`` / ``.xlsx``）を含めて指定する。拡張子は名前の文字列にだけ書く。引数 ``ext`` / ``extension`` は廃止済みのため使えない。 |
| `InvalidCredentialNameError` | 認証情報のキー名に使えない文字がある | 半角英数字とアンダースコアだけにする（漢字・スペース・記号は使えない） |
| `CredentialNotFoundError` | 認証情報（パスワード・client_secret など）が登録されていない | 表示された登録済みキー名と見比べる。無ければ `python -m comken cred import 認証情報.json` で取り込む |
| `CredentialDecryptionError` | 認証情報を復号できない | 登録したときと**同じ Windows アカウント・同じ PC** で実行しているか確認する。タスクスケジューラの実行ユーザー違いが最も多い |
| `CredentialStoreCorruptedError` | 認証情報の中身が壊れている | 実行アカウントの問題ではない。表示されたファイルを削除して、もう一度取り込み直す |
| `CredentialImportError` | 取り込む JSON が壊れている・形式が違う | 表示された形式のとおりに書き直す。値は必ず `" "` で囲む |
| `SalesforceAuthError` | Salesforce にログインできない | 表示された確認項目を上から順に見る。それでも直らなければ管理者へ連絡する |
| `SalesforceConnectionError` | Salesforce につながらない | ネットワークの状態を確認して、少し待ってから再実行する |
| `SalesforceRequestError` | Salesforce が処理を断った | 表示されたメッセージをそのまま添えて管理者へ連絡する（権限か項目名の問題が多い） |
| `SalesforceExternalIDMissingError` | upsert 用データに外部 ID がない | 管理者へ連絡する |
| `SalesforceCredentialRotationError` | consumer key / secret のローテーションを安全に完了できない | Salesforce の ECA 設定・API レスポンス・DPAPI の保存先を確認する |
| `SalesforceReportTruncatedError` | レポートが上限の 2000 行で切れた（**全件ではない**） | 期間を狭めて何回かに分けて実行する。1回で全部必要なら管理者へ連絡する |
| `SalesforceReportFormatError` | レポートの形式が対応していない | レポートを明細形式にするか、管理者へ連絡する |
| `SalesforceReportIDNotFoundError` | レポートの URL からレポート ID を取り出せない | Salesforce でレポートを開いたときのアドレスを、そのまま貼り直す |
| `SalesforceReportExecutionError` | Salesforce 側でレポート実行に失敗した | Salesforce で同じレポートを直接実行し、表示された内容を管理者へ連絡する |
| `SalesforceReportAccessDeniedError` | レポート API（Reports and Dashboards REST API）へのアクセスを拒否された | Salesforce 管理者に、実行ユーザー（Client Credentials では Run As ユーザー）について次を確認してもらう。1. Profile / Permission Set に「API Enabled」権限があるか2. 対象のレポート・レポートフォルダへのアクセス権があるか3. 組織の Edition・ライセンスが Reports and Dashboards REST APIに対応しているか（一部の制限ライセンスでは使えない） |
| `SalesforceSiteNotFoundError` | URL のドメインに対応する組織が登録されていない | URL のドメインを見直す。新しい組織なら管理者へ連絡する（組織クラスの追加が要る） |
| `MasterTableError` | Excel の管理表に関するエラー | 画面に表示された具体的なエラー名を上の表から探す |
| `MasterSheetNotDefinedError` | 管理表の場所が決まっていない | `load(パス)` のようにファイルを渡すか、クラスに PATH を書く（コードの直し方の話なので、非エンジニアが見た場合は管理者へ連絡する） |
| `MasterColumnNotFoundError` | 管理表に必要な列（見出し）が無い | 管理表の1行目（見出し）を元に戻す。消してしまった場合は、メッセージに出ている「今ある見出し」と見比べて足す |
| `MasterRowValueError` | 管理表の値が正しくない | メッセージに出ている行と列を、管理表で確認して直す |
| `MasterDuplicateValueError` | 一意であるべき列に、同じ値が2つ以上ある | 管理表を開いて、重複している値のどちらかを別の値に変える |
| `StateFileCorruptedError` | state.ini が壊れていて読み取れない | 内容を直す。直せない場合は別名に変更して、空の状態から再実行する |
| `StateLowerCaseNameError` | state のキー名に小文字がある | 表示されたキー名を大文字に直す（`last_file` → `LAST_FILE`） |
| `StateValueTypeError` | state に保存できない型の値が渡された | 真偽値・整数・小数・文字列・文字列のリストのいずれかに変更する |
| `BusinessDayNotFoundError` | 営業日が見つからなかった | n をその月の営業日数以下に直す、対象月の祝日に過不足がないか確認する、社内管理表（会社休日）が広範囲に登録されていないか確認する |
| `HolidayCalendarError` | 祝日カレンダーに関するエラー | 画面に表示された具体的なエラー名を上の表から探す |
| `HolidayCalendarSourceError` | 祝日データの読み取りに失敗した | 内閣府の CSV の場合: 内閣府の仕様変更。管理者へ連絡する |
| `HolidayCalendarFormatError` | 内閣府 CSV 以外のファイルや壊れたファイルを内閣府 CSV として読み込もうとした | 内閣府の syukujitsu.csv を直接取得し直す。文字コードは CP932 (Shift_JIS) |
| `HistoryWriteError` | 必須のダウンロード履歴を記録できなかった | 履歴CSVの保存先、共有サーバー接続、書込み権限を確認する |
| `HistoryLockTimeoutError` | ダウンロード履歴の排他ロックを待っても取得できなかった | 同時実行中の処理が終わるのを待って再実行する。繰り返す場合は共有サーバーを確認する |
| `HistoryHeaderMismatchError` | ダウンロード履歴CSVの見出しが現在の定義と一致しない | 履歴CSVの1行目を確認する。列を手で変更していた場合は元へ戻し、古い形式の履歴なら別名へ退避してから再実行する |
| `CachedReportNotFoundError` | 本日の定期取得キャッシュが見つからない | Salesforce からCSVを手動取得し、画面に表示された正確なパス・ファイル名で置いて、同じ python main.py を再実行する |
| `ReportNotRegisteredError` | 指定した管理番号が管理表に無い | 管理表を開いて、その管理番号の行があるか確認する。新しく使うレポートは、先に管理表へ登録する |
| `ReportDisabledError` | 管理表で「無効」になっているレポートを取ろうとした | また使うなら管理表の「有効」を「有効」に戻す。使わないなら、呼び出し側のコードから消す |
| `InvalidReportURLError` | 管理表の URL から Salesforce のレポート ID を取り出せない | Salesforce でレポートを開いたときのアドレスを、そのまま貼り直す |
| `EmptyReportError` | レポートは実行できたが明細が 0 行だった | Salesforce の画面で同じレポートを開き、本当に 0 件か確認する。0 件が正常に起こるレポートなら、管理表の「0件あり」を「○」にする。 |
| `ReportFolderNotFoundError` | 管理表に書かれた保存先のフォルダが無い | 管理表の「保存先」を確認する。共有フォルダなら、つながっているか・権限があるかも確認する |
| `ReportReservePathLimitError` | 保存ファイル名の連番が上限に達した | 保存先フォルダが想定どおりか確認する。 共有フォルダなら、 古い取得ファイルを退避するか、 別の保存先に変える。 連発する場合は権限・排他制御の設定も見直す |
| `ScheduledDownloadFailedError` | 定期取得で1件以上が失敗した | 履歴（ダウンロード履歴.csv）の「エラー内容」で、失敗した理由を確認する。急いで必要なものは download_scheduled() をスケジュール外で実行する。権限を持つ人が Salesforce から手動でダウンロードしてもよい |
| `UnsupportedScheduleFrequencyError` | 管理表の「取得頻度」に、想定外の値が書かれている | 管理表の「取得頻度」列の値を ``1時間ごと`` / ``毎日`` / ``毎週`` /``毎月`` のいずれかに修正する |
| `ScheduleIntervalMissingError` | 「1時間ごと」の行で、開始・終了・間隔のどれかが抜けている | 管理表の「取得開始時刻」「取得終了時刻」「取得間隔（分）」の3列をすべて埋める |
| `ScheduleRequiredValueMissingError` | 管理表の必須列が空になっている | 管理表の該当行で、表示された列名（スケジュールキー / レポートキー /取得頻度）の値を埋める |
| `ScheduleWeekdayInvalidError` | 管理表の「曜日」列に想定外の値が入っている | 管理表の「曜日」列の値を月〜日のいずれかに修正する（「曜日」を付ける形式でも可） |
| `ScheduleRowValueError` | スケジュール管理表の行の値が正しくない | メッセージに出ている行と直したい値を、管理表で確認して直す |
| `ScheduleDuplicateKeyError` | スケジュール管理表の「スケジュールキー」が重複している | スケジュール管理表を開いて、重複しているスケジュールキーのどちらかを別の値に変える |
| `LoggingAlreadyConfiguredError` | root logger がすでに設定されている | setup_logging() または setup_local_logging() はアプリの入口で1回だけ呼ぶ。実行基盤がログを設定する場合は呼ばない。 |
| `LoggingConflictError` | root logger に comken 以外の handler が設定されている | 上の handler 一覧をそのままライブラリの管理者へ連絡してください（連絡先は環境ごとに異なるので、ここには書かない）。やむを得ず共存させたい場合は、呼び出し時に ``allow_existing=True``を指定すれば処理は続きますが、comken のハンドラーが追加されることで既存ライブラリのログが**二重**に出たり、出力先が想定と変わる可能性があります。 |
| `LogRootNotConfiguredError` | LoggerSite の LOG_ROOT が設定されていない | サブクラスに ``LOG_ROOT = "\\server\share\logs"`` を1行追加する（絶対パスまたは UNC 文字列。LOG_FOLDER_NAMES のフォルダ名はこの下に作られる）。 |
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
| `SiteAlreadyInLibraryError` | ライブラリ公認のサイトと同じ NAME のサイトをプロジェクト側で定義した | ライブラリから `from comken.toolbox.browser.sites import <クラス名>` で取り出して使う。プロジェクト側の定義は消す。ライブラリへ昇格する基準は`docs/開発/ライブラリ開発規約.md` を参照。 |
| `SiteNotStartedError` | まだ起動していないサイトの画面を作ろうとした | `with Kintai() as kintai:` の中で使う |
| `ElementNotFoundError` | 画面の部品が時間内に見つからない | もう一度実行する。サイトが重いだけのことが多い。毎回出るなら画面が変わった可能性があるので管理者へ（エラーに、どの部品を探していたかが出ます） |
| `PopupTabNotOpenedError` | 別タブが開かない | もう一度実行する。続く場合は、その画面の「別ウィンドウで開く」ボタンが変わった可能性があるので管理者へ |
| `DownloadTimeoutError` | ダウンロードが終わらない | ネットワークの状態を確認して再実行する。大きいファイルなら時間がかかっているだけのこともある |
| `WebDriverException` | ブラウザ操作の一般的なエラー | Edge のウィンドウをすべて閉じて再実行する |

## Table のエラー

| エラー名 | 意味 | 自分でできる対処 |
|---|---|---|
| `TransferDestinationMultipleMatchError` | 転記先のキーに一致する行が複数ある | mapping の先頭列に対応する転記先列の値を一意にする。キーが ``None`` か ``""`` の行は突合対象外なので、空欄のキーが複数あってもこの例外は出ない。 |
| `TableNotOpenError` | 表を with 文で開かずに操作した。 | ``with`` 文の中で使う（CSV / Excel などは ``__enter__`` で表を開く） |
| `TransferDestinationMissingError` | Transfer.apply_mapping() に転記先が None で渡された | matched_rows() を使うか、``transfer_rows()`` の ``(read_row, None)``を ``if write_row is None:`` で分岐してから渡す。 新規行を追加する場合は ``Transfer`` の責務ではなく、``Table.append()`` 等で利用者側で対応する。 |
| `InvalidTableInputError` | Table API に対応しない入力が渡された。 | columns、rows、types の型と列名を確認する |
| `InvalidTableOperationError` | Table API で実行できない操作が指定された。 | 対象が読み取り専用でないか、指定したテーブル名が正しいか確認する |
| `TableColumnNotFoundError` | Table に指定された列が存在しない。 | Table.columns を確認し、存在する列名を指定する |
| `TableDuplicateKeyError` | Table の索引または比較に使うキーが重複している。 | キー列の値を一意にしてから処理をやり直す |
| `TableRowColumnsError` | 行の列名が Table.columns と一致しない | 不足列と余分な列を直す。列を絞る場合は select() を使う |
| `TableTypeConversionError` | Table の値を指定型へ変換できない | 表示された行番号・列名の値を、指定した型へ変換できる内容に直す |

## Windows 操作のエラー

| エラー名 | 意味 | 自分でできる対処 |
|---|---|---|
| `WindowNotFoundError` | 指定したウィンドウが見つからない | 対象ウィンドウが開いているか、タイトル（完全一致）が想定どおりかを確認する |

## 分類（まとめて捕捉する用）

次の名前は、似たエラーをプログラム側でまとめて扱うための分類です。
これらの名前が単独で表示されることはありません。対処するときは、画面に表示された
具体的なエラー名を上の表から探してください。

| エラー名 | 意味 | 自分でできる対処 |
|---|---|---|
| `ComkenError` | comken が出す固有エラー全体 | 画面に表示された具体的なエラー名を上の表から探す |
| `ExcelError` | Excel に関するエラー | 画面に表示された具体的なエラー名を上の表から探す |
| `AccessError` | Access に関するエラー | 画面に表示された具体的なエラー名を上の表から探す |
| `CSVError` | CSV に関するエラー | 画面に表示された具体的なエラー名を上の表から探す |
| `ColumnNotFoundError` | Excel・CSV・データ比較で列が見つからないエラー | 画面に表示された具体的なエラー名を上の表から探す |
| `ConfigError` | config.ini に関するエラー | 画面に表示された具体的なエラー名を上の表から探す |
| `StateError` | state.ini に関するエラー | 画面に表示された具体的なエラー名を上の表から探す |
| `DownloaderError` | Salesforce レポートの集約取得に関するエラー | 画面に表示された具体的なエラー名を上の表から探す |
| `SalesforceError` | Salesforce に関するエラー | 画面に表示された具体的なエラー名を上の表から探す |
| `CredentialError` | 認証情報の保存・取得に関するエラー | 画面に表示された具体的なエラー名を上の表から探す |
| `BrowserError` | ブラウザ操作に関するエラー | 画面に表示された具体的なエラー名を上の表から探す |
| `TableError` | 表データの読み書き・転記に関するエラー | 画面に表示された具体的なエラー内容を確認する |
| `InternalLibraryError` | 社内ライブラリの呼び出しに失敗したときの基底例外 | 画面に表示された具体的なエラー名（NotFound / VersionMismatch）を上の表から探す |
