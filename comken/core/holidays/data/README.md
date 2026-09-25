# comken/core/holidays/data/

会社用カレンダーの元データ置き場。**`company_calendar.csv` を直接編集してはいけません**。
元データを変えたら、必ず `python -m comken.core.holidays.build` を実行して
`company_calendar.csv` を再生成してください。

## 2 つの CSV

| ファイル | 役割 | 編集していい？ |
|---|---|---|
| `syukujitsu.csv` | 内閣府の祝日一覧（CP932） | 更新手順で差し替え |
| `company_calendar.csv` | 生成物（Python/VBA が読む正本） | **いいえ**（`build` で再生成） |

会社の休業日は CSV ではなく、`comken/core/holidays/build.py` の冒頭
（`COMPANY_HOLIDAYS` / `COMPANY_HOLIDAYS_EXTRA`）に書きます。

## 会社休日を変える

1. `comken/core/holidays/build.py` 冒頭の定数を直す
   - 毎年の休み: `COMPANY_HOLIDAYS` に `(月, 日)` を足す
   - その年だけの休み: `COMPANY_HOLIDAYS_EXTRA` に `date(2026, 12, 28)` のように足す
2. `python -m comken.core.holidays.build` を実行
3. `company_calendar.csv` の変更をまとめてコミット

国民の祝日と重なると **国民の祝日が先勝ち** します。

## 年 1 回の内閣府 CSV 更新手順

1. 内閣府の `syukujitsu.csv` をダウンロード（<https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv>）
2. ダウンロードしたファイルで `syukujitsu.csv` を上書き（CP932 のまま）
3. `python -m comken.core.holidays.build` を実行して `company_calendar.csv` を再生成
4. `syukujitsu.csv` と `company_calendar.csv` の更新をまとめてコミット・タグ打ち
