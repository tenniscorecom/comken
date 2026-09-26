"""comken/core/holidays/__init__.py — 祝日カレンダー判定ライブラリ。

「国民の祝日 + 会社休日」を 1 ファイルに合成した **会社用カレンダー CSV**
（``comken/core/holidays/data/company_calendar.csv``）を読み、
「今日が営業日か」「次の営業日」「収録期限の警告」を提供する。

    from comken.core import holidays

    if holidays.is_workday(date.today()):
        ...  # レポートを取りに行く

``workday(d, n)`` は Excel の ``WORKDAY(d, n)`` と同じ。

ライブラリは **既定カレンダー 1 本だけ** を公開する。利用者が独自の
カレンダーを組み立てる API は公開しない（会社休日を変えるときは
``comken/core/holidays/build.py`` 冒頭の ``COMPANY_HOLIDAYS`` を直す）。

実行時は内閣府 CSV も会社休日のルールも持たない。会社休日・国民の祝日の
判定は **生成物である 1 ファイル** だけを読んで行うため、内閣府 CSV の
形式変更は生成ツールだけが対応すればよい。

**年 1 回の手動更新**（開発機で内閣府から取得 →
``python -m comken holidays`` を実行 → ``company_calendar.csv``
をコミット）で配布する。自動ダウンロード機能は無い。

HOLIDAYS_CSV_PATH           会社用カレンダーCSV のパス（git 管理下の正本）
WORKDAY_SEARCH_LIMIT        「次の営業日」探索の日数上限
EXPIRING_WARNING_DAYS       期限切れ警告を出すまでの日数
is_holiday                  国民の祝日または会社休日に当たれば True
holiday_name                国民の祝日または会社休日の名称（無ければ None）
is_workday                  簡易判定（国民の祝日＋会社休日＋土日）
workday                     target から n 営業日後（n=0 ならそのまま、負なら前）
                             Excel の WORKDAY 互換
count_workdays              start から end までの両端を含む営業日数
                             Excel の NETWORKDAYS 互換
workday_on_or_after         d 以降で最初の営業日（d 自身を含む）
workday_on_or_before        d 以前で最初の営業日（d 自身を含む）
first_workday               d の月の最初の営業日
last_workday                d の月の最後の営業日
nth_workday                 d の月の第 n 営業日（n は 1 以上）
non_workdays_after          d の翌日から次の営業日の前日までの休みの日（連休）
non_workdays_before         d の前日から前の営業日の翌日までの休みの日（連休）
warn_if_holidays_expiring_soon  既定カレンダーの収録期限が近ければ起動時に警告
WorkdayNotFoundError        月内に該当営業日が無い／探索上限到達
HolidayError                祝日カレンダーに関する基底例外
"""

from comken.core.holidays._holidays import (
    EXPIRING_WARNING_DAYS,
    HOLIDAYS_CSV_PATH,
    WORKDAY_SEARCH_LIMIT,
    count_workdays,
    first_workday,
    holiday_name,
    is_holiday,
    is_workday,
    last_workday,
    non_workdays_after,
    non_workdays_before,
    nth_workday,
    warn_if_holidays_expiring_soon,
    workday,
    workday_on_or_after,
    workday_on_or_before,
)
from comken.exceptions import HolidayError, WorkdayNotFoundError

__all__ = [
    "EXPIRING_WARNING_DAYS",
    "HOLIDAYS_CSV_PATH",
    "HolidayError",
    "WORKDAY_SEARCH_LIMIT",
    "WorkdayNotFoundError",
    "count_workdays",
    "first_workday",
    "holiday_name",
    "is_holiday",
    "is_workday",
    "last_workday",
    "non_workdays_after",
    "non_workdays_before",
    "nth_workday",
    "warn_if_holidays_expiring_soon",
    "workday",
    "workday_on_or_after",
    "workday_on_or_before",
]
