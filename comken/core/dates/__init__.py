"""comken/core/dates/__init__.py — 日付・祝日・営業日・年度まわりのユーティリティ。

業務で使う日付計算・祝日判定・営業日オフセットを 1 パッケージにまとめる。
「国民の祝日 + 会社休日」を 1 ファイルに合成した **会社用カレンダー CSV**
（``comken/core/dates/data/company_calendar.csv``）を読み、「今日が営業日か」
「次の営業日」「収録期限の警告」を提供する。

    from comken.core import dates

    if dates.is_workday(date.today()):
        ...  # レポートを取りに行く

``workday(d, n)`` は Excel の ``WORKDAY(d, n)`` と同じ。

ライブラリは **既定カレンダー 1 本だけ** を公開する。利用者が独自の
カレンダーを組み立てる API は公開しない（会社休日を変えるときは
``comken/core/dates/build.py`` 冒頭の ``COMPANY_HOLIDAYS`` を直す）。

実行時は内閣府 CSV も会社休日のルールも持たない。会社休日・国民の祝日の
判定は **生成物である 1 ファイル** だけを読んで行うため、内閣府 CSV の
形式変更は生成ツールだけが対応すればよい。

**年 1 回の手動更新**（開発機で内閣府から取得 →
``python -m comken holidays`` を実行 → ``company_calendar.csv``
をコミット）で配布する。自動ダウンロード機能は無い。

now / today                     この PC のローカル「今の時刻」「今日の日付」
month_start / month_end         その月の 1 日 / 末日
parse_cell_date                 セルの値を date に（読めなければ None）
date_in_name                    ファイル名に含まれる最初の日付（無ければ None）
fiscal_year                     その日付が属する年度（4 月始まり）
is_holiday                      国民の祝日または会社休日に当たれば True
holiday_name                    国民の祝日または会社休日の名称（無ければ None）
is_workday                      簡易判定（国民の祝日＋会社休日＋土日）
workday                         target から n 営業日後（n=0 ならそのまま、負なら前）
                                Excel の WORKDAY 互換
count_workdays                  start から end までの両端を含む営業日数
                                Excel の NETWORKDAYS 互換
workday_on_or_after             d 以降で最初の営業日（d 自身を含む）
workday_on_or_before            d 以前で最初の営業日（d 自身を含む）
first_workday                   d の月の最初の営業日
last_workday                    d の月の最後の営業日
nth_workday                     d の月の第 n 営業日（n は 1 以上）
non_workdays_after              d の翌日から次の営業日の前日までの休みの日（連休）
non_workdays_before             d の前日から前の営業日の翌日までの休みの日（連休）

``HolidayError`` / ``WorkdayNotFoundError`` は ``comken.exceptions`` から取る
（``from comken.exceptions import ...``）。
``warn_if_holidays_expiring_soon`` / ``WORKDAY_SEARCH_LIMIT`` /
``EXPIRING_WARNING_DAYS`` / ``HOLIDAYS_CSV_PATH`` / ``FISCAL_YEAR_START_MONTH``
は内部実装。comken の起動時に ``comken/run.py`` から ``comken.core.dates._holidays``
/ ``comken.core.dates._fiscal`` 経由で直接 import して使う。
"""

from comken.core.dates._dates import (
    date_in_name,
    month_end,
    month_start,
    now,
    parse_cell_date,
    today,
)
from comken.core.dates._fiscal import fiscal_year
from comken.core.dates._holidays import (
    count_workdays,
    first_workday,
    holiday_name,
    is_holiday,
    is_workday,
    last_workday,
    non_workdays_after,
    non_workdays_before,
    nth_workday,
    workday,
    workday_on_or_after,
    workday_on_or_before,
)

__all__ = [
    "count_workdays",
    "date_in_name",
    "fiscal_year",
    "first_workday",
    "holiday_name",
    "is_holiday",
    "is_workday",
    "last_workday",
    "month_end",
    "month_start",
    "non_workdays_after",
    "non_workdays_before",
    "now",
    "nth_workday",
    "parse_cell_date",
    "today",
    "workday",
    "workday_on_or_after",
    "workday_on_or_before",
]
