# comken/core/calendar/data/

会社用カレンダーの元データ置き場。**`company_calendar.csv` を直接編集しては
いけません**。編集後は必ず `python -m comken.core.calendar.build` を実行して
`company_calendar.csv` を再生成してください。

## 3 つの CSV

| ファイル | 役割 | 編集していい？ |
|---|---|---|
| `syukujitsu.csv` | 内閣府の祝日一覧（CP932） | 更新手順で差し替え |
| `company_holidays.csv` | **会社の休業日ルール**（UTF-8 BOM 付き・CRLF） | **はい** |
| `company_calendar.csv` | 生成物（Python/VBA が読む正本） | **いいえ**（`build` で再生成） |

## 会社休日を追加する

`company_holidays.csv` を Excel で開いて行を足します（月の列・日の列は
別々の数字で書いてください。日付形式は NG）。

- **毎年繰り返す休み** — 年を空欄にする（例: `, 7, 20, 夏季休暇`）
- **その年だけの臨時休業** — 年に数字を書く（例: `2026, 12, 28, 会社休業日`）

国民の祝日と重なると **国民の祝日が先勝ち** します。

## 編集後の手順

1. `company_holidays.csv` を保存
2. リポジトリ直下で `python -m comken.core.calendar.build` を実行
3. `company_calendar.csv` の変更をまとめてコミット

## 年 1 回の内閣府 CSV 更新手順

1. 内閣府の `syukujitsu.csv` をダウンロード（<https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv>）
2. ダウンロードしたファイルで `syukujitsu.csv` を上書き（CP932 のまま）
3. `python -m comken.core.calendar.build` を実行して `company_calendar.csv` を再生成
4. `syukujitsu.csv` と `company_calendar.csv` の更新をまとめてコミット・タグ打ち