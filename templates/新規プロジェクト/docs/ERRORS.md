# エラー対応ガイド

エラーが出たら、**黒い画面（コンソール）の一番下あたりに出ている「エラー名」**をこの表から探してください。
エラー名は `SheetNotFoundError` のような英語の単語です。

> このファイルは comken の雛形です。プロジェクトで使うときはルートにコピーし、
> そのプロジェクト固有のエラーと対処を追記してください。

---

## まず試すこと（どのエラーでも共通）

1. 開いている Excel ファイルをすべて閉じて、もう一度実行する
2. それでもダメなら、このガイドでエラー名を探す
3. 表にない・解決しない場合は、**エラーの画面全体をスクリーンショット**して管理者に送る

---

## Excel のエラー

| エラー名 | 意味 | 自分でできる対処 |
|---|---|---|
| `SheetNotFoundError` | 指定した名前のシートがない | Excel を開いて、下のシート名（タブ）が変わっていないか確認する。変えた場合は元に戻す |
| `SheetAlreadyExistsError` | 同じ名前のシートが既にある | 別のシート名を指定するか、既存のシート名を変更する |
| `LastSheetDeletionError` | ブックの最後のシートを削除しようとした | 先に別のシートを追加してから削除する |
| `InvalidTableNameError` | Excel で使えないテーブル名を指定した | 空白・数字始まり・セル参照のような名前を避ける |
| `TableAlreadyExistsError` | 同じ名前のテーブルが既にある | 別のテーブル名を指定する |
| `TableNotFoundError` | 指定したテーブルがシートにない | エラーに表示された既存テーブル名を確認する |
| `ExcelFileNotFoundError` | Excel ファイルが見つからない | ファイルの置き場所と名前を確認する |
| `ExcelFormulaError` | 再計算した数式に `#NAME?` / `#REF!` 等がある | 表示されたシート・セルの数式、参照先、テーブル名、列名を確認する |
| `ExcelColumnNotFoundError` | Excel の列見出しが見つからない | Excel の1行目を確認する |
| `MacroError` | Excel のマクロが失敗した | Excel をすべて閉じて再実行する。続く場合は管理者へ |
| `RowTransferError` | Excel の行転記に失敗した | 表示された行番号のデータを確認する |
| `EmptyHeaderCellError` | Excel の見出しに空欄がある | Excel の1行目の空欄を埋める |
| `ExcelHeadersTooFewError` | 指定した見出し数が列数より少ない | 管理者へ連絡する |

## Access のエラー

| エラー名 | 意味 | 対処 |
|---|---|---|
| `AccessFileNotFoundError` | Access ファイルが見つからない | ファイルの置き場所と名前を確認する |
| `AccessBackupError` | 元 DB を開く前のバックアップに失敗した | 保存先の空き容量・書き込み権限・元 DB の読み取り権限を確認する |
| `AccessLocalCopyError` | Access ファイルを一時フォルダへコピーできない | 使用状況・読み取り権限・空き容量を確認する |
| `AccessRoutineError` | Access マクロまたは VBA の実行に失敗した | 表示された名前と Access 側の内容を確認する |
| `AccessSourceNotFoundError` | テーブルまたはクエリが見つからない | エラーに表示された存在する名前を確認する |
| `FileFormatMismatchError` | 保存拡張子と形式が合わない | 管理者へ連絡する |
| `PermissionError` | ファイルが誰かに開かれている | 自分や他の人がそのファイルを開いていないか確認して閉じる |

---

## ファイルのエラー

| エラー名 | 意味 | 自分でできる対処 |
|---|---|---|
| `FileNotFoundError` | ファイルが見つからない | ファイルの置き場所と名前を確認する。「今日の日付のファイル」を探す処理なら、今日のファイルが作られているか確認する |
| `TimeoutError` | ダウンロードが終わらない | ネットワークの状態を確認して再実行する |
| `UnsupportedFileSuffixError` | 対応外の拡張子が指定された | CSV / Excel の対応する拡張子のファイルを指定する |
| `EncodingDetectionError` | CSV の文字コードを判定できない | CSV の保存形式を確認し、管理者へ連絡する |
| `CsvHeadersTooFewError` | 指定した見出し数が CSV の列数より少ない | 管理者へ連絡する |
| `CsvNoDataRowsError` | CSV に見出し以外のデータ行がない | 見出し行の下にデータが1行以上あるか確認する |
| `CsvCellReferenceError` | CSV のセル位置（例: A2）の指定が正しくない、または範囲外 | 表示されたセル位置と、CSV の行数・列数を確認する |
| `CsvColumnNotFoundError` | CSV の列見出しが見つからない | CSV の1行目を確認する |
| `KeyColumnNotFoundError` | 比較に使うキー列が見つからない | Excel・CSV の列名を確認する |
| `InvalidColumnError` | 列の指定が正しくない（打ち間違いなど） | 列は番号（1, 2, …）か列記号（"A", "AA"）で指定する |
| `ConfigFileNotFoundError` | config.ini が見つからない | config.ini.example をコピーして config.ini を作る |
| `ConfigSectionNotFoundError` | config.ini の必要な節がない | 表示されたセクション名を config.ini に追加する |

---

## 分類（まとめて捕捉する用）

次の名前は、似たエラーをプログラム側でまとめて扱うための分類です。
これらの名前が単独で表示されることはありません。対処するときは、画面に表示された
具体的なエラー名を上の表から探してください。

| 分類名 | まとめるエラー |
|---|---|
| `OriginalLibsError` | comken が出す固有エラー全体 |
| `ExcelError` | Excel に関するエラー |
| `AccessError` | Access に関するエラー |
| `CsvError` | CSV に関するエラー |
| `ColumnNotFoundError` | Excel・CSV・データ比較で列が見つからないエラー |
| `ConfigError` | config.ini に関するエラー |

---

## ブラウザ（Edge 自動操作）のエラー

| エラー名 | 意味 | 自分でできる対処 |
|---|---|---|
| `TimeoutException` | 画面の表示待ちで時間切れ | もう一度実行する。サイトが重いだけのことが多い。毎回出るなら画面が変わった可能性があるので管理者へ |
| `NoSuchElementException` | 画面の部品が見つからない | サイトの画面が変わった可能性が高い。管理者へ |
| `SessionNotCreatedException` | Edge とドライバーのバージョン不一致 | Windows Update で Edge が更新された直後に起きる。管理者へ（msedgedriver の更新が必要） |
| `WebDriverException` | ブラウザ操作の一般的なエラー | Edge のウィンドウをすべて閉じて再実行する |

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
## Outlook のエラー

| エラー名 | 意味 | 対処 |
|---|---|---|
| `OutlookError` | Outlook 関連エラーの分類 | 下の個別エラーを確認する |
| `ClassicOutlookNotAvailableError` | Classic Outlook を利用できない | Classic Outlook を使うか管理者に相談する |
| `OutlookFolderNotFoundError` | 指定したフォルダがない | エラーに表示された存在するフォルダ名を確認する |
| `OutlookAttachmentNotFoundError` | 添付ファイルがない | 表示されたファイルパスを確認する |
