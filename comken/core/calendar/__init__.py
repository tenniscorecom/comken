"""comken/core/calendar/__init__.py — 祝日カレンダー判定ライブラリ。

内閣府の祝日 CSV を **ライブラリ同梱の 1ファイル**から読み、
「今日が営業日か」「次の営業日」「収録期限の警告」を提供する。

    from comken.core.calendar import is_business_day

    if is_business_day(date.today()):
        ...  # レポートを取りに行く

ライブラリは **既定カレンダー 1 本だけ** を公開する。利用者が独自の
カレンダーを組み立てる API は公開しない（会社休日はこのライブラリの
管理者が ``comken/core/calendar/company.py`` の ``COMPANY_HOLIDAYS`` /
``COMPANY_HOLIDAYS_EXTRA`` にコードで追加する）。

国民の祝日（内閣府 CSV + 計算式）と会社休日をマージして判定する。
国民の祝日と会社休日が同じ日に重なった場合は **国民の祝日が先勝ち**。
会社休日は実行時に ``(月, 日)`` ルールで毎回判定するため、年範囲の
管理は不要（過去・未来を問わず年末年始が休みになる）。

内閣府 CSV は ``BUNDLED_CSV_PATH``（= ``comken/core/calendar/data/syukujitsu.csv``）
に **git 管理下で併して** いる。**PC ごとのキャッシュは持たない**。
更新は年 1 回の手動作業（**開発機で内閣府から取得 → コミット → 共有サーバーへ checkout**）。

BUNDLED_CSV_PATH             内閣府 CSV を併しているパス（正本）。git 管理下。
EXPORTED_CSV_PATH            export_csv() の既定の書き出し先。git 管理下。
                              Excel・VBA 側はここを参照すればよい
is_holiday                    国民の祝日または会社休日に当たれば True
holiday_name                  国民の祝日または会社休日の名称（無ければ None）
is_business_day               簡易判定（国民の祝日＋会社休日＋土日）
business_day_after            ``target`` より後で最初の営業日（``target`` を含まない）
business_day_before           ``target`` より前で最初の営業日（``target`` を含まない）
business_day_on_or_after      ``target`` 以降で最初の営業日（``target`` を含む）
business_day_on_or_before     ``target`` 以前で最初の営業日（``target`` を含む）
first_business_day_of_month   ``target`` の月の最初の営業日
last_business_day_of_month    ``target`` の月の最後の営業日
nth_business_day_of_month     ``target`` の月の第 n 営業日（n は 1 始まり）
add_business_days             ``target`` から n 営業日後（n が負なら前）
export_csv                    国民の祝日＋会社休日を 1948-2099 年ぶんの CSV へ書き出す
warn_if_calendar_expiring_soon 既定カレンダーの収録期限が近ければ起動時に警告
CalendarError                祝日カレンダーに関する基底例外
BusinessDayNotFoundError      月内に該当営業日が無い／探索上限到達
CalendarSourceError           祝日データの読み取りに関する基底例外
CalendarFormatError           内閣府 CSV として解釈できない形式
"""

from comken.core.calendar._calendar import (
    BUNDLED_CSV_PATH,
    BUSINESS_DAY_SEARCH_LIMIT,
    EXPIRING_WARNING_DAYS,
    EXPORTED_CSV_PATH,
    add_business_days,
    business_day_after,
    business_day_before,
    business_day_on_or_after,
    business_day_on_or_before,
    export_csv,
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
    CalendarSourceError,
)

__all__ = [
    "BUNDLED_CSV_PATH",
    "BUSINESS_DAY_SEARCH_LIMIT",
    "BusinessDayNotFoundError",
    "CalendarError",
    "CalendarFormatError",
    "CalendarSourceError",
    "EXPIRING_WARNING_DAYS",
    "EXPORTED_CSV_PATH",
    "add_business_days",
    "business_day_after",
    "business_day_before",
    "business_day_on_or_after",
    "business_day_on_or_before",
    "export_csv",
    "first_business_day_of_month",
    "holiday_name",
    "is_business_day",
    "is_holiday",
    "last_business_day_of_month",
    "nth_business_day_of_month",
    "warn_if_calendar_expiring_soon",
]
