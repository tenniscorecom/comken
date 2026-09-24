# comken.core.calendar — カレンダー判定ライブラリ

RPA 置き換えプロジェクトで「いま取るべきレポートか」を判定するために使う、
内閣府の祝日 CSV を基にした営業日判定ライブラリ。

実装本体は `comken/core/calendar/` 配下にある（外部ライブラリに依存しない）。
国民の祝日 CSV は **git 管理下の 1 ファイル**として
`comken/core/calendar/data/syukujitsu.csv` に同梱されており、年 1 回の
**手動更新**（後述）で配布する。自動ダウンロード機能は廃止した（YAGNI）。

ライブラリは **既定カレンダー 1 本だけ**を公開する。利用者が独自のカレンダーを
組み立てる API は公開していない（差し替え口はテスト用の **非公開** 関数のみ）。
会社独自の休業日は `comken/core/calendar/company.py` の **コード直書き**で
表現する——`COMPANY_HOLIDAYS`（年単位の月日ルール）と `COMPANY_HOLIDAYS_EXTRA`
（特定年月日の例外）の 2 つの定数を管理者が編集する。

国民の祝日（内閣府 CSV + 計算値）と会社休日をマージして、`is_business_day()`
で「今日が営業日か」を判定する。国民の祝日と会社休日が同じ日に重なった場合は
**国民の祝日が先勝ち**（国民の祝日の名称が返る）。

## 最短の使い方

```python
from datetime import date

from comken.core.calendar import is_business_day

if is_business_day(date.today()):     # 既定カレンダーで判定
    ...  # レポートを取りに行く
```

`is_business_day` / `business_day_after` / `last_business_day_of_month` /
`is_holiday` / `holiday_name` などは **既定カレンダー**をそのまま使う。
カレンダーを組み立てる API は公開していない。

## 取得元

| ソース                      | 概要                                                       | 必要なもの            |
| --------------------------- | ---------------------------------------------------------- | --------------------- |
| 内部実装（計算ソース） | 純粋計算で国民の祝日を組み立てる（mokejp/holidays_jp MIT 由来） | 標準ライブラリのみ |
| 内閣府 CSV（`syukujitsu.csv`）| 国民の祝日の確定値（内部実装で上書き）                       | 標準ライブラリのみ   |
| `company.py` のルール      | 会社独自の休業日（年単位の月日 + 特定年月日）              | 標準ライブラリのみ    |

会社休日は専用のソースを持たず、**実行時に毎回ルール判定**する
（`company_holiday_name(date)` が月日を見て名前を返す）。これは内閣府 CSV の
ような「データでカバーする」方式だと範囲外の日付をカバーできないためで、
会社休日は範囲を固定せず **過去・未来問わず年末年始休暇などの月日が休み**に
なるようにしている。

## 内閣府 CSV の同梱（既定カレンダー）

既定カレンダーは内閣府の `syukujitsu.csv` を `comken/core/calendar/data/` に
**同梱**している。業務 PC がオフラインでも `is_business_day()` はそのまま動く。

- **年 1 回手動で更新する**（開発機で内閣府から取得 → コミット → 共有サーバーへ checkout）。
  自動ダウンロード機能は無い
- 収録期限（= 同梱 CSV に書かれた最新日付）が近づくと `EXPIRING_WARNING_DAYS`（既定 30 日）
  未満で **WARNING ログが 1 度だけ**出る（更新タイミングの検知）
- 期限を過ぎても止まらず純粋計算（mokejp/holidays_jp 由来）でカバーする
  春分・秋分のみ内閣府発表日との ±1 日のずれが起きうる
- 会社休日はコード判定なので期限を持たない（年末年始休暇は 2090 年でも休みになる）

### 年 1 回の手動更新手順

1. 開発機で内閣府の `syukujitsu.csv` をダウンロードする
   （URL: <https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv>）
2. `comken/core/calendar/data/syukujitsu.csv` をダウンロードしたファイルで上書きする
3. `python tools\export_calendar.py` を実行して `data/holidays.csv` を再生成する
4. `syukujitsu.csv` と `holidays.csv` をまとめてコミットし、タグを打つ
5. 共有サーバー側で `git fetch --tags && git checkout <tag>` して配布する

## 会社休日

会社の休業日は `comken/core/calendar/company.py` にコードで書く。
設定ファイルや管理表を編集する運用負荷は要らない。

```python
# comken/core/calendar/company.py
COMPANY_HOLIDAYS: Final[dict[str, tuple[tuple[int, int], ...]]] = {
    "年末年始休暇": ((12, 29), (12, 30), (12, 31), (1, 1), (1, 2), (1, 3)),
}

# その年だけの臨時の休み。年月日で書く
COMPANY_HOLIDAYS_EXTRA: Final[tuple[_dt.date, ...]] = ()
```

**年が書いてない月日のリスト**で表現するので、毎年のメンテナンスが要らない
のが要点（過去・未来を問わず同じ月日が休みになる）。

休業日を追加するときは `company.py` 冒頭の定数を編集する。

- 「年末年始休暇」のような**複数日まとめて 1 つ**の名称が要るときは
  `COMPANY_HOLIDAYS` のキーに `((月, 日), (月, 日), …)` のタプルを書く
- 1 日だけの休業は `((月, 日),)` のように 1 要素のタプルにする
- 年またぎ（12 月 → 1 月）も月日の連なりで書けばそのまま毎年適用される
- **その年だけ臨時の休み**を足したいときは `COMPANY_HOLIDAYS_EXTRA` に
  `date(2026, 12, 28)` のように年月日で 1 行足す。古くなった行は消してよい
  （消しても過去の判定が変わるだけで、運用に影響しない）

## Excel・VBA 向け CSV（`data/holidays.csv`）

国民の祝日と会社休日を 1948-2099 年ぶんの CSV として
`comken/core/calendar/data/holidays.csv` に書き出している（git 管理下）。
列は `date`（`YYYY-MM-DD`）・`name`・`approximate`（`True`/`False`）の 3 列。
エンコーディングは `utf-8-sig`（BOM 付き UTF-8）で、Excel でそのまま開ける。

呼び出した日（実行時の今日）に依存せず、結果は固定:

- 国民の祝日は内閣府 CSV が定める範囲（1948-2099）
- 会社休日は `COMPANY_HOLIDAYS` の `(月, 日)` ルールで毎回判定

国民の祝日と同じ日に会社休日に当たる日（例: 2026/1/1 = 元日 + 年末年始休暇）は
**国民の祝日が先勝ち**で 1 行だけ書き出される。

更新は以下のタイミングで **手動**で行う:

1. 内閣府 CSV を差し替えたとき（年 1 回）
2. `company.py` のルールを変更したとき

```bash
python tools\export_calendar.py
```

オプションで書き出し先を指定できる:

```bash
python tools\export_calendar.py --path tmp\out.csv
```

## 期限切れの警告

収録済み祝日のうち最も新しい日付を「収録最終日」とし、
「今日」が収録最終日に近づいたら WARNING ログを出す。

| 状況                                | 挙動                                                                  |
| ----------------------------------- | --------------------------------------------------------------------- |
| 今日 < 収録最終日 − 30 日           | 警告なし                                                              |
| 収録最終日 − 30 日 <= 今日 <= 収録最終日 | WARNING ログを **同じ日に 1 度だけ** 出す                            |
| 今日 > 収録最終日                   | 警告なしで動くが、`is_holiday()` は常に `False`（「祝日ではない」側） |

期限切れ後はあえて「祝日ではない」側に倒す——誤って「祝日扱い」にしてレポートを
取り逃すより、誤って「平日扱い」して RPA を走らせ、次回ログから気付く方が
被害が少ないため。

## 公開 API

| 名前                              | 役割                                                       |
| --------------------------------- | ---------------------------------------------------------- |
| `is_holiday(d)`                   | 国民の祝日または会社休日に当たれば `True`                  |
| `holiday_name(d)`                 | 国民の祝日または会社休日の名称を返す（無ければ `None`）    |
| `is_business_day(d, *, skip_weekends=True)` | 国民の祝日＋会社休日＋土日を判定して `True`/`False` |
| `business_day_after(d, *, skip_weekends=True)` | `d` より後で最初の営業日（`d` 自身を含まない）     |
| `business_day_before(d, *, skip_weekends=True)` | `d` より前で最初の営業日（`d` 自身を含まない）     |
| `business_day_on_or_after(d, *, skip_weekends=True)` | `d` 以降で最初の営業日（`d` を含む）           |
| `business_day_on_or_before(d, *, skip_weekends=True)` | `d` 以前で最初の営業日（`d` を含む）           |
| `first_business_day_of_month(d, *, skip_weekends=True)` | `d` の月の最初の営業日                 |
| `last_business_day_of_month(d, *, skip_weekends=True)` | `d` の月の最後の営業日                  |
| `nth_business_day_of_month(d, n, *, skip_weekends=True)` | `d` の月の第 `n` 営業日（`n` は 1 始まり） |
| `add_business_days(d, n, *, skip_weekends=True)` | `d` から `n` 営業日後の日付（`n` が負なら前）           |
| `export_csv(path=None, *, encoding='utf-8-sig')` | 国民の祝日＋会社休日を 1948-2099 年ぶんの CSV に書き出す |
| `warn_if_calendar_expiring_soon()` | 既定カレンダーの収録期限が近ければ起動時に WARNING を出す  |
| `BUSINESS_DAY_SEARCH_LIMIT`       | 「次の営業日」探索の上限日数（既定 30）                     |
| `EXPIRING_WARNING_DAYS`           | 期限切れ警告を出すまでの日数（既定 30）                     |
| `BUNDLED_CSV_PATH`                | 内閣府 CSV を同梱しているパス（git 管理下の正本）           |
| `EXPORTED_CSV_PATH`               | `export_csv()` の既定の書き出し先（`data/holidays.csv`）     |
| `CalendarError` 系               | 例外（`CalendarSourceError` / `CalendarFormatError` / `BusinessDayNotFoundError`） |

`skip_weekends=False` にすると土曜・日曜でも祝日でなければ「営業日」と
判定する（振替休日を平日扱いしたいシナリオ用）。
このフラグは `business_day_after` / `first_business_day_of_month` など、
他の営業日オフセット計算にも同じキーワード専用で渡せる。

### 営業日オフセットの選び方

`after` / `before` は「その日を含まない」、`on_or_after` / `on_or_before` は
「その日を含む」。営業日かどうかにかかわらず、必ずしも「その日が答え」に
なるわけではないので、要件に合わせて選ぶ。

```python
from datetime import date
from comken.core.calendar import (
    business_day_after,
    business_day_on_or_before,
    last_business_day_of_month,
    nth_business_day_of_month,
)

# 月末の最終営業日（例: 月末が土日祝なら直前の営業日）
last_business_day_of_month(date(2026, 8, 20))

# 月初の営業日（例: 1日が土日祝なら翌営業日）
first_business_day_of_month(date(2026, 8, 20))

# 第 3 営業日
nth_business_day_of_month(date(2026, 8, 20), 3)

# 15 日、休みならその前の営業日
business_day_on_or_before(date(2026, 8, 15))

# 8/20 の「翌営業日」。8/20 が営業日でも翌営業日が返る
business_day_after(date(2026, 8, 20))
```

`business_day_after(d)` は `d` 自身が営業日でも翌日以降を返す点に注意。
「今日から 1 営業日後」を `add_business_days(d, 1)` で書いた場合は、
`d` が営業日でも翌営業日（n 営業日分進む）が返る。
「翌営業日」と「1 営業日後」は別物なので、目的に合わせて使い分ける。

| 関数                    | `d` が営業日のとき | `d` が非営業日のとき         |
| ----------------------- | ------------------ | ---------------------------- |
| `business_day_after`    | `d` の次の営業日   | `d` より後で最初の営業日     |
| `business_day_before`   | `d` の前の営業日   | `d` より前で最初の営業日     |
| `business_day_on_or_after`  | `d` 自身       | `d` 以降で最初の営業日       |
| `business_day_on_or_before` | `d` 自身       | `d` 以前で最初の営業日       |

「`d` を含むかどうか」だけが違うので、「`d` が営業日のときにスキップして
ほしくない」ケースは `on_or_*` を選ぶ。

`nth_business_day_of_month` は、`n` が月の営業日数を超える場合と、その月に
営業日が 1 日も無い場合のどちらも `BusinessDayNotFoundError`。

## 注意事項

- **国民の祝日名・会社休日名は業務情報ではない**ため、ドキュメント・ログに
  出してよい（`docs/csv.md` の「値そのもの」の禁止とは別）。
- 国民の祝日と会社休日が同じ日に重なった場合は**国民の祝日が先勝ち**
  （国民の祝日の名称が返る）。
- 国民の祝日データ期限を過ぎても止まらず計算式が
  カバーする（春分・秋分のみ内閣府発表日との ±1 日のずれが起きうる）。
- 内閣府 CSV 以外のファイル（シフト JIS でない・日付列が無いなど）を
  内閣府 CSV として読み込もうとすると `CalendarFormatError` で止める。
- **ネットワークには一切出ない。** `comken.core` は `requests` を import
  しないので、オフライン環境・社内 BO 端末でもそのまま動く。

## 関連

- 内閣府: <https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv>
- comken 仕様書: `docs/開発/仕様書.md`
- comken 例外階層: `comken/exceptions/__init__.py`