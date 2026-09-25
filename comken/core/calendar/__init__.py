"""comken/core/calendar/__init__.py — 祝日カレンダー判定ライブラリ。

「国民の祝日 + 会社休日」を 1 ファイルに合成した **会社用カレンダー CSV**
（``comken/core/calendar/data/company_calendar.csv``）を読み、
「今日が営業日か」「次の営業日」「収録期限の警告」を提供する。

    from comken.core.calendar import is_business_day

    if is_business_day(date.today()):
        ...  # レポートを取りに行く

ライブラリは **既定カレンダー 1 本だけ** を公開する。利用者が独自の
カレンダーを組み立てる API は公開しない（会社休日を変えるときは
``comken/core/calendar/data/company_holidays.csv`` を編集する）。

実行時は内閣府 CSV も会社休日のルールも持たない。会社休日・国民の祝日の
判定は **生成物である 1 ファイル** だけを読んで行うため、内閣府 CSV の
形式変更は生成ツールだけが対応すればよい。

**年 1 回の手動更新**（開発機で内閣府から取得 →
``python -m comken.core.calendar.build`` を実行 → ``company_calendar.csv``
をコミット）で配布する。自動ダウンロード機能は無い。

CALENDAR_CSV_PATH             会社用カレンダーCSV のパス（git 管理下の正本）
BUSINESS_DAY_SEARCH_LIMIT     「次の営業日」探索の日数上限
EXPIRING_WARNING_DAYS         期限切れ警告を出すまでの日数
is_holiday                    国民の祝日または会社休日に当たれば True
holiday_name                  国民の祝日または会社休日の名称（無ければ None）
is_business_day               簡易判定（国民の祝日＋会社休日＋土日）
business_day_after/before/on_or_after/on_or_before  営業日オフセット
first/last/nth_business_day_of_month               月初・月末・第N営業日
add_business_days             target から n 営業日後（n が負なら前）
warn_if_calendar_expiring_soon 既定カレンダーの収録期限が近ければ起動時に警告
BusinessDayNotFoundError      月内に該当営業日が無い／探索上限到達
CalendarError                 祝日カレンダーに関する基底例外
CalendarFormatError           会社用カレンダーCSV として解釈できない形式
"""

from comken.core.calendar._calendar import (
    BUSINESS_DAY_SEARCH_LIMIT,
    CALENDAR_CSV_PATH,
    EXPIRING_WARNING_DAYS,
    add_business_days,
    business_day_after,
    business_day_before,
    business_day_on_or_after,
    business_day_on_or_before,
    first_business_day_of_month,
    holiday_name,
    is_business_day,
    is_holiday,
    last_business_day_of_month,
    nth_business_day_of_month,
    warn_if_calendar_expiring_soon,
)
from comken.exceptions import (
    BusinessDayNotFoundError,
    CalendarError,
    CalendarFormatError,
)

__all__ = [
    "BUSINESS_DAY_SEARCH_LIMIT",
    "BusinessDayNotFoundError",
    "CALENDAR_CSV_PATH",
    "CalendarError",
    "CalendarFormatError",
    "EXPIRING_WARNING_DAYS",
    "add_business_days",
    "business_day_after",
    "business_day_before",
    "business_day_on_or_after",
    "business_day_on_or_before",
    "first_business_day_of_month",
    "holiday_name",
    "is_business_day",
    "is_holiday",
    "last_business_day_of_month",
    "nth_business_day_of_month",
    "warn_if_calendar_expiring_soon",
]
