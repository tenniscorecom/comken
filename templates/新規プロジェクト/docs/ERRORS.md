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
| `ExcelFileNotFoundError` | Excel ファイルが見つからない | ファイルの置き場所と名前を確認する |
| `ExcelColumnNotFoundError` | Excel の列見出しが見つからない | Excel の1行目を確認する |
| `MacroError` | Excel のマクロが失敗した | Excel をすべて閉じて再実行する。続く場合は管理者へ |
| `RowTransferError` | Excel の行転記に失敗した | 表示された行番号のデータを確認する |
| `EmptyHeaderCellError` | Excel の見出しに空欄がある | Excel の1行目の空欄を埋める |
| `ExcelHeadersTooFewError` | 指定した見出し数が列数より少ない | 管理者へ連絡する |
| `FileFormatMismatchError` | 保存拡張子と形式が合わない | 管理者へ連絡する |
| `PermissionError` | ファイルが誰かに開かれている | 自分や他の人がそのファイルを開いていないか確認して閉じる |

---

## ファイルのエラー

| エラー名 | 意味 | 自分でできる対処 |
|---|---|---|
| `FileNotFoundError` | ファイルが見つからない | ファイルの置き場所と名前を確認する。「今日の日付のファイル」を探す処理なら、今日のファイルが作られているか確認する |
| `TimeoutError` | ダウンロードが終わらない | ネットワークの状態を確認して再実行する |
| `EncodingDetectionError` | CSV の文字コードを判定できない | CSV の保存形式を確認し、管理者へ連絡する |
| `CsvHeadersTooFewError` | 指定した見出し数が CSV の列数より少ない | 管理者へ連絡する |
| `CsvColumnNotFoundError` | CSV の列見出しが見つからない | CSV の1行目を確認する |
| `KeyColumnNotFoundError` | 比較に使うキー列が見つからない | Excel・CSV の列名を確認する |
| `ConfigFileNotFoundError` | config.ini が見つからない | config.ini.example をコピーして config.ini を作る |
| `ConfigSectionNotFoundError` | config.ini の必要な節がない | 表示されたセクション名を config.ini に追加する |

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
