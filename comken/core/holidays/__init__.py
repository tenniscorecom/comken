r"""comken/core/holidays/__init__.py — 祝日判定ライブラリ。

内閣府の祝日 CSV をダウンロードしてキャッシュし、
「今日が営業日か」「次の営業日」「収録期限の警告」を提供する。

    from comken.core.holidays import HolidayCalendar, is_business_day
    from comken.toolbox.holidays.sources.cabinet_office import CabinetOfficeCSVSource

    calendar = HolidayCalendar.from_sources([
        CabinetOfficeCSVSource(cache_path=Path("~/.comken/holidays/syukujitsu.csv")),
        CompanyHolidaySource(),
    ])

    if is_business_day(date.today(), calendar=calendar):
        ...  # レポートを取りに行く

遅延 import 禁止の方針どおり、requests はモジュール import 時には読み込まない。
ネット系の処理は ``sources.cabinet_office.CabinetOfficeCSVSource`` の中だけに閉じ、
``HolidayCalendar.is_business_day`` 単体ではネットに繋がらずに動く。

営業日の判定関数（``is_business_day`` / ``business_day_after`` /
``business_day_on_or_after`` / ``first_business_day_of_month`` など）は
``calendar`` を省略できる簡易版も公開している。省略時は **既定カレンダー**
（``ComputedHolidaySource`` + 同梱 ``syukujitsu.csv`` + ``CompanyHolidaySource``）
が使われ、ネットワークには出ない。会社独自の休日を追加したいときは
``set_default_calendar()`` で差し替える。

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
CabinetOfficeCSVSource    内閣府 CSV を URL + キャッシュで取得する ``HolidaySource``
ComputedHolidaySource     計算式で祝日を組み立てる ``HolidaySource``
CompanyHolidaySource      会社独自の休業日（コード直書き）の ``HolidaySource``
HolidayCalendarError  祝日関連の基底例外
BusinessDayNotFoundError   月内に該当営業日が無い／探索上限到達
HolidayCalendarFetchError      内閣府 CSV の取得失敗
HolidayCalendarSourceError     管理表・CSV 形式の問題
HolidayCalendarFormatError     内閣府 CSV として解釈できない形式
"""

from comken.core.holidays.calendar import (
    BUSINESS_DAY_SEARCH_LIMIT,
    EXPIRING_WARNING_DAYS,
    Holiday,
    HolidayCalendar,
    HolidaySource,
    RefreshableHolidaySource,
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
    HolidayCalendarFetchError,
    HolidayCalendarFormatError,
    HolidayCalendarSourceError,
)

__all__ = [
    "BUSINESS_DAY_SEARCH_LIMIT",
    "BusinessDayNotFoundError",
    "CompanyHolidaySource",
    "ComputedHolidaySource",
    "EXPIRING_WARNING_DAYS",
    "Holiday",
    "HolidayCalendar",
    "HolidayCalendarError",
    "HolidayCalendarFetchError",
    "HolidayCalendarFormatError",
    "HolidayCalendarSourceError",
    "HolidaySource",
    "RefreshableHolidaySource",
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
