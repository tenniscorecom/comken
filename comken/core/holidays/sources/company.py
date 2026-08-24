"""comken/core/holidays/sources/company.py — 会社独自の休業日ソース。

``ComputedHolidaySource`` が国民の祝日を法律から組み立てるのに対し、
このソースは**会社都合の休業日**（年末年始休暇など）をコードに直書きして返す。
国民の祝日とは別の概念なので、別のソースに切り出して運用する。

- 国民の祝日と重なっても**先勝ちで採用**されるので、名称が書き換わっても
  業務影響が無いように ``COMPANY_HOLIDAYS`` のキーは日本語名称をそのまま使う
- 土日と重なっても振替は行わない（この会社は土日出勤・振替休日が無い前提）
- 「その年だけ出勤にする」機能は持たない。必要になったら別途足す
"""

import datetime as _dt
from typing import Final

from comken.core.holidays.calendar import Holiday, HolidaySource

# 毎年繰り返す会社の休業日。**年は書かない**（毎年その月日が休みになる）。
# 休みを増やすときは (月, 日) を書き足すだけでよい。年またぎの年末年始も
# 月日で書けばそのまま毎年適用される。
COMPANY_HOLIDAYS: Final[dict[str, tuple[tuple[int, int], ...]]] = {
    "年末年始休暇": ((12, 29), (12, 30), (12, 31), (1, 1), (1, 2), (1, 3)),
}

# その年だけの臨時の休み。年月日で書く。
# 例: 2026年だけ 12/28 も休みにする → date(2026, 12, 28) を足す。
# 古くなった年の行は消してよい（消しても過去の判定が変わるだけで、運用に影響しない）。
COMPANY_HOLIDAYS_EXTRA: Final[tuple[_dt.date, ...]] = ()

EXTRA_HOLIDAY_NAME: Final[str] = "会社休業日"

# 会社休日を生成する範囲。既定はソースの寿命全体を賄うため広めに取ってある。
DEFAULT_FROM_YEAR: Final[int] = 1900
DEFAULT_TO_YEAR: Final[int] = 2200


class CompanyHolidaySource(HolidaySource):
    """コードに直書きした会社休日を ``Holiday`` の iterable で返すソース。

    ``HolidaySource`` Protocol を実装する。既定カレンダーは
    ``default_calendar()`` が組み立てるので、利用者が自分で
    ``HolidayCalendar.from_sources(...)`` を書く必要はない
    （使うだけなら ``is_business_day(today())`` と書く）。

    国民の祝日（内閣府 CSV / Computed）と重なったときは**先勝ち**で
    採用される（``HolidayCalendar`` 側の挙動）。警告は出さない。

    このソースは **外部 I/O を一切しない** 純粋な Python 計算。
    社内 BO 環境（オフライン・pip 制限）でもそのまま動く。

    Args:
        from_year: 対象範囲の開始年。省略時は ``DEFAULT_FROM_YEAR`` (1900)。
        to_year: 対象範囲の終了年。省略時は ``DEFAULT_TO_YEAR`` (2200)。
    """

    def __init__(
        self,
        *,
        from_year: int | None = None,
        to_year: int | None = None,
    ) -> None:
        self._from_year = from_year if from_year is not None else DEFAULT_FROM_YEAR
        self._to_year = to_year if to_year is not None else DEFAULT_TO_YEAR
        if self._from_year > self._to_year:
            raise ValueError(
                f"from_year ({self._from_year}) が to_year ({self._to_year}) より大きいです。"
            )

    def load(self) -> list[Holiday]:
        """会社休日を ``Holiday`` のリストで返す。

        日付順に並べた状態で返す。国民の祝日と重なっても気にせずそのまま出す
        （``HolidayCalendar`` 側で先勝ち採用される）。
        """
        holidays: list[Holiday] = [
            Holiday(date=extra_date, name=EXTRA_HOLIDAY_NAME)
            for extra_date in COMPANY_HOLIDAYS_EXTRA
            if self._from_year <= extra_date.year <= self._to_year
        ]
        for year in range(self._from_year, self._to_year + 1):
            for name, month_days in COMPANY_HOLIDAYS.items():
                for month, day in month_days:
                    holidays.append(Holiday(date=_dt.date(year, month, day), name=name))
        return sorted(holidays, key=lambda h: h.date)


__all__ = [
    "COMPANY_HOLIDAYS",
    "COMPANY_HOLIDAYS_EXTRA",
    "CompanyHolidaySource",
    "DEFAULT_FROM_YEAR",
    "DEFAULT_TO_YEAR",
    "EXTRA_HOLIDAY_NAME",
]
