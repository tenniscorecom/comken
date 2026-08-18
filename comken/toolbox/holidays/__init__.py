r"""comken/toolbox/holidays/__init__.py — 祝日判定ライブラリ。

内閣府の祝日 CSV をダウンロードしてキャッシュし、
「今日が営業日か」「次の営業日」「収録期限の警告」を提供する。

    from comken.toolbox.holidays import HolidayCalendar, is_business_day

    calendar = HolidayCalendar.from_sources([
        CabinetOfficeCsvSource(cache_path=Path("~/.comken/holidays/syukujitsu.csv")),
        ComkenMasterTableSource(Path(r"\\server\share\管理表.xlsx")),
    ])

    if is_business_day(date.today(), calendar=calendar):
        ...  # レポートを取りに行く

遅延 import 禁止の方針どおり、requests はモジュール import 時には読み込まない。
ネット系の処理は ``sources.cabinet_office.CabinetOfficeCsvSource`` の中だけに閉じ、
``HolidayCalendar.is_business_day`` 単体ではネットに繋がらずに動く。

HolidayCalendar       祝日セットを保持し判定を行う本体
HolidaySource         祝日セットを返す仕組みの Protocol
Holiday               1件の祝日（日付 + 名称）
is_business_day       ``HolidayCalendar`` を引数に取る簡易判定
CabinetOfficeCsvSource    内閣府 CSV を URL + キャッシュで取得する ``HolidaySource``
ComkenMasterTableSource   社内管理表の「会社休日」シートを読む ``HolidaySource``
HolidayCalendarError  祝日関連の基底例外
HolidayCalendarFetchError      内閣府 CSV の取得失敗
HolidayCalendarSourceError     管理表・CSV 形式の問題
HolidayCalendarFormatError     内閣府 CSV として解釈できない形式
HolidayCalendarExpiredError    収録期限切れ
"""

from comken.toolbox.holidays.calendar import (
    EXPIRING_WARNING_DAYS,
    Holiday,
    HolidayCalendar,
    HolidaySource,
    is_business_day,
)
from comken.toolbox.holidays.exceptions import (
    HolidayCalendarError,
    HolidayCalendarExpiredError,
    HolidayCalendarFetchError,
    HolidayCalendarFormatError,
    HolidayCalendarSourceError,
)
from comken.toolbox.holidays.sources.cabinet_office import CabinetOfficeCsvSource
from comken.toolbox.holidays.sources.master_table import ComkenMasterTableSource

__all__ = [
    "CabinetOfficeCsvSource",
    "ComkenMasterTableSource",
    "EXPIRING_WARNING_DAYS",
    "Holiday",
    "HolidayCalendar",
    "HolidayCalendarError",
    "HolidayCalendarExpiredError",
    "HolidayCalendarFetchError",
    "HolidayCalendarFormatError",
    "HolidayCalendarSourceError",
    "HolidaySource",
    "is_business_day",
]
