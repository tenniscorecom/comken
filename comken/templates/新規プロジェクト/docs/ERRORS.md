# エラー対応ガイド

エラーが出たら、**黒い画面（コンソール）の一番下あたりに出ている「エラー名」**をこの表から探してください。
エラー名は `SheetNotFoundError` のような英語の単語です。

> **このプロジェクトで出たエラーと対処を、下の表に追記してください。**

---

## まず試すこと（どのエラーでも共通）

1. 開いている Excel ファイルをすべて閉じて、もう一度実行する
2. それでもダメなら、このガイドでエラー名を探す
3. 表にない・解決しない場合は、**エラーの画面全体をスクリーンショット**して管理者に送る

| エラー名 | 意味 | 自分でできる対処 |
|---|---|---|
| `ModuleNotFoundError: No module named 'comken'` | 共有サーバーの comken を読み込めない | 共有サーバーに繋がっているか確認する。繋がっているなら `実行.bat` の `PYTHON_LIBRARY` の場所が正しいかを管理者に確認する |

---

## Excel のエラー

| エラー名 | 意味 | 自分でできる対処 |
|---|---|---|
| `SheetNotFoundError` | 指定した名前のシートがない | Excel を開いて、下のシート名（タブ）が変わっていないか確認する。変えた場合は元に戻す |
| `ExcelApplicationNotAvailableError` | Excel を起動できない | この PC に Excel が入っているか確認する。入れられない PC で動かすなら、数式ではなく値で書いてもらう（管理表なら、数式の結果を貼り付けてもらう） |
| `ColumnNotFoundError` | 列が見つからない | Excel の1行目を確認する |
| `TableError` | 表データの読み書き・転記に関するエラー（with 文の外で操作した／テーブルが一意に決まらない／`engine='com'` で `Sheet` 系 API を呼んだ等。具体的な理由はメッセージに出る） | メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ |

## Access のエラー

| エラー名 | 意味 | 対処 |
|---|---|---|
| `AccessBackupError` | 元 DB を開く前のバックアップに失敗した | 保存先の空き容量・書き込み権限・元 DB の読み取り権限を確認する |
| `AccessLocalCopyError` | Access ファイルを一時フォルダへコピーできない | 使用状況・読み取り権限・空き容量を確認する |
| `AccessRoutineError` | Access マクロまたは VBA の実行に失敗した | 表示された名前と Access 側の内容を確認する |
| `AccessSourceNotFoundError` | テーブルまたはクエリが見つからない | エラーに表示された存在する名前を確認する |
| `PermissionError` | ファイルが誰かに開かれている | 自分や他の人がそのファイルを開いていないか確認して閉じる |

---

## ファイルのエラー

| エラー名 | 意味 | 自分でできる対処 |
|---|---|---|
| `FileNotFoundError` | ファイルが見つからない | ファイルの置き場所と名前を確認する。「今日の日付のファイル」を探す処理なら、今日のファイルが作られているか確認する |
| `ComkenFileNotFoundError` | ファイル・フォルダが見つからない（対象はメッセージに出る） | メッセージに表示された対象（Excel ファイル / CSV ファイル / Access ファイル / config.ini / Outlook 添付 / Data Loader 実行ファイル / 結果 CSV / 保存先フォルダ 等）とパスを見てして、置き場所と名前を確認する |
| `TimeoutError` | ダウンロードが終わらない | ネットワークの状態を確認して再実行する |
| `UnsupportedFileSuffixError` | 対応外の拡張子が指定された | CSV / Excel の対応する拡張子のファイルを指定する |
| `InvalidColumnError` | 列の指定が正しくない（打ち間違いなど） | 列は番号（1, 2, …）か列記号（"A", "AA"）で指定する |
| `ConfigCreatedFromExampleError` | config.ini が無かったので example から作った | 作られた config.ini の値を書き換えて、もう一度実行する |
| `ConfigLowerCaseNameError` | config.ini のセクション名・キー名に小文字がある | 表示された名前を大文字に書き換える（`[files]` → `[FILES]`） |
| `ConfigSectionNotFoundError` | config.ini の必要な節がない | 表示されたセクション名を config.ini に追加する |

---

## 分類（まとめて捕捉する用）

次の名前は、似たエラーをプログラム側でまとめて扱うための分類です。
これらの名前が単独で表示されることはありません。対処するときは、画面に表示された
具体的なエラー名を上の表から探してください。

| 分類名 | まとめるエラー |
|---|---|
| `ComkenError` | comken が出す固有エラー全体 |
| `ExcelError` | Excel に関するエラー |
| `AccessError` | Access に関するエラー |
| `CSVError` | CSV に関するエラー |
| `ColumnNotFoundError` | Excel・CSV・データ比較で列が見つからないエラー |
| `TableError` | 表データの読み書き・転記に関するエラー |
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

## Outlook のエラー

| エラー名 | 意味 | 対処 |
|---|---|---|
| `OutlookError` | Outlook 関連エラーの分類 | 下の個別エラーを確認する |
| `ClassicOutlookNotAvailableError` | Classic Outlook を利用できない | Classic Outlook を使うか管理者に相談する |
| `OutlookFolderNotFoundError` | 指定したフォルダがない | エラーに表示された存在するフォルダ名を確認する |

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