r"""comken/core/holidays/__init__.py — 祝日判定ライブラリ。

内閣府の祝日 CSV を **ライブラリ同梱の 1ファイル**から読み、
「今日が営業日か」「次の営業日」「収録期限の警告」を提供する。

    from comken.core.holidays import HolidayCalendar, is_business_day

    # 利用プロジェクトでは ``HolidayCalendar`` に会社の休業日を足すだけで
    # 動かせる形が基本。
    calendar = HolidayCalendar.from_sources([
        CompanyHolidaySource(),
    ])

    if is_business_day(date.today(), calendar=calendar):
        ...  # レポートを取りに行く

内閣府 CSV は ``BUNDLED_CSV_PATH``（= ``comken/core/holidays/data/syukujitsu.csv``）
に **git 管理下で同梱** している。**PC ごとのキャッシュは持たない**。
更新は年 1 回の手動作業（**開発機で内閣府から取得 → コミット → 共有サーバーへ checkout**）。

営業日の判定関数（``is_business_day`` / ``business_day_after`` /
``business_day_on_or_after`` / ``first_business_day_of_month`` など）は
``calendar`` を省略できる簡易版も公開している。省略時は **既定カレンダー**
（``ComputedHolidaySource`` + 同梱 ``syukujitsu.csv`` + ``CompanyHolidaySource``）
が使われ、ネットワークには出ない。会社独自の休日を追加したいときは
``set_default_calendar()`` で差し替える。

BUNDLED_CSV_PATH             内閣府 CSV を同梱しているパス（正本）。git 管理下。
HolidayCalendar       祝日セットを保持し判定を行う本体
HolidaySource         祝日セットを返す仕組みの Protocol
Holiday               1件の祝日（日付 + 名称）
is_business_day           簡易判定（``calendar`` 省略可）
business_day_after        ``target`` より後で最初の営業日（``target`` を含まない）
business_day_before       ``target`` より前で最初の営業日（``target`` を含まない）
business_day_on_or_after  ``target`` 以降で最初の営業日（``target`` を含む）
business_day_on_or_before ``target`` 以前で最初の営業日（``target`` を含む）
first_business_day_of_month  ``target`` の月の最初の営業日
last_business_day_of_month   ``target`` の月の最後の営業日
nth_business_day_of_month    ``target`` の月の第 n 営業日（n は 1 始まり）
add_business_days            ``target`` から n 営業日後（n が負なら前）
default_calendar             既定カレンダーを取得（プロセス内で 1回だけ遅延生成）
set_default_calendar         既定カレンダーを差し替える（``None`` でリセット）
ComputedHolidaySource     計算式で祝日を組み立てる ``HolidaySource``
CompanyHolidaySource      会社独自の休業日（コード直書き）の ``HolidaySource``
HolidayCalendarError  祝日関連の基底例外
BusinessDayNotFoundError   月内に該当営業日が無い／探索上限到達
HolidayCalendarSourceError     管理表・CSV 形式の問題
HolidayCalendarFormatError     内閣府 CSV として解釈できない形式
"""

from comken.core.holidays.calendar import (
    BUNDLED_CSV_PATH,
    BUSINESS_DAY_SEARCH_LIMIT,
    EXPIRING_WARNING_DAYS,
    Holiday,
    HolidayCalendar,
    HolidaySource,
    add_business_days,
    business_day_after,
    business_day_before,
    business_day_on_or_after,
    business_day_on_or_before,
    default_calendar,
    first_business_day_of_month,
    is_business_day,
    last_business_day_of_month,
    nth_business_day_of_month,
    set_default_calendar,
)
from comken.core.holidays.csv_source import load_cabinet_office_csv
from comken.core.holidays.sources.company import CompanyHolidaySource
from comken.core.holidays.sources.computed import ComputedHolidaySource
from comken.exceptions import (
    BusinessDayNotFoundError,
    HolidayCalendarError,
    HolidayCalendarFormatError,
    HolidayCalendarSourceError,
)

__all__ = [
    "BUNDLED_CSV_PATH",
    "BUSINESS_DAY_SEARCH_LIMIT",
    "BusinessDayNotFoundError",
    "CompanyHolidaySource",
    "ComputedHolidaySource",
    "EXPIRING_WARNING_DAYS",
    "Holiday",
    "HolidayCalendar",
    "HolidayCalendarError",
    "HolidayCalendarFormatError",
    "HolidayCalendarSourceError",
    "HolidaySource",
    "add_business_days",
    "business_day_after",
    "business_day_before",
    "business_day_on_or_after",
    "business_day_on_or_before",
    "default_calendar",
    "first_business_day_of_month",
    "is_business_day",
    "last_business_day_of_month",
    "load_cabinet_office_csv",
    "nth_business_day_of_month",
    "set_default_calendar",
]
