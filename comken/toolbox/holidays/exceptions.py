"""comken/toolbox/holidays/exceptions.py — 祝日ライブラリ独自の例外 re-export。

個別例外は comken/exceptions に集約しているが、このモジュールから
import する書き方を好む利用側のために短い名前で再公開する。
"""

from comken.exceptions import (
    HolidayCalendarError,
    HolidayCalendarExpiredError,
    HolidayCalendarFetchError,
    HolidayCalendarFormatError,
    HolidayCalendarSourceError,
)

__all__ = [
    "HolidayCalendarError",
    "HolidayCalendarFetchError",
    "HolidayCalendarSourceError",
    "HolidayCalendarFormatError",
    "HolidayCalendarExpiredError",
]
