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
import logging
from typing import Final

from comken.core import clock
from comken.core.holidays.calendar import Holiday, HolidaySource

logger = logging.getLogger(__name__)

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

# 会社休日を生成する既定の対象範囲。「実行時の今日」を基準に前後何年ぶんを
# カバーするかを、この 2 定数で決める。固定の 1900-2200（301 年ぶん）のように
# ソースの寿命全体を賄う範囲にすると、年末年始休暇だけで約 1800 件が生成され、
# 業務で触らない日付までメモリに抱える。
#
# 過去側は ``DEFAULT_YEARS_BACK`` 年ぶん（業務で参照する日付は今日の過去
# 数十年以内に収まるため）。先は ``DEFAULT_YEARS_AHEAD = 1`` で**来年まで**に
# 留める — 内閣府の祝日 CSV（``data/syukujitsu.csv``）が来年分までしか公表
# されないので、年末年始休暇も来年分までしか生成しない。来年より先で営業日
# 計算をしたいときは ``to_year`` を明示してこのソースの対象範囲を広げること
# （国民の祝日側は ``ComputedHolidaySource`` が 2099 年まで計算するので、
# 同じ範囲に広げれば先の日付でも国民の祝日＋年末年始休暇が揃う）。
DEFAULT_YEARS_BACK: Final[int] = 40
DEFAULT_YEARS_AHEAD: Final[int] = 1


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

    既定の対象範囲は「実行時の今日 - ``DEFAULT_YEARS_BACK`` 年 〜 実行時の
    今年 + ``DEFAULT_YEARS_AHEAD`` 年」。

    .. note::
        **既定では来年分までしか生成しない。** 内閣府の祝日 CSV
        （``data/syukujitsu.csv``）が「実行時の今年の翌年」分までしか
        公表されないため、それに揃えて年末年始休暇も来年分までに留めてある。
        **既定の範囲外の日付には会社休日（年末年始休暇）が付かない** ので、
        来年より先の日付では「国民の祝日は付くが年末年始休暇は付かない」
        という状態になる（国民の祝日は別ソース ``ComputedHolidaySource`` が
        2099 年まで計算する）。先の日付まで含めて営業日計算をしたいときは
        ``to_year`` を明示する。

    Args:
        from_year: 対象範囲の開始年。省略時は「実行時の今日の年 - ``DEFAULT_YEARS_BACK``」。
        to_year: 対象範囲の終了年。省略時は「実行時の今日の年 +
            ``DEFAULT_YEARS_AHEAD`` 年」（既定の ``DEFAULT_YEARS_AHEAD = 1``
            で来年分まで）。
    """

    def __init__(
        self,
        *,
        from_year: int | None = None,
        to_year: int | None = None,
    ) -> None:
        # 「今日」は comken.core.clock.today() から取る。datetime.date.today() を
        # 直接呼ばないのは、テストで日付を固定できるようにするため。
        current_year = clock.today().year
        self._from_year = from_year if from_year is not None else current_year - DEFAULT_YEARS_BACK
        self._to_year = to_year if to_year is not None else current_year + DEFAULT_YEARS_AHEAD
        if self._from_year > self._to_year:
            raise ValueError(
                f"from_year ({self._from_year}) が to_year ({self._to_year}) より大きいです。"
            )
        logger.debug(
            "CompanyHolidaySource 構築: from_year=%d, to_year=%d",
            self._from_year,
            self._to_year,
        )

    def load(self) -> list[Holiday]:
        """会社休日を ``Holiday`` のリストで返す。

        日付順に並べた状態で返す。国民の祝日と重なっても気にせずそのまま出す
        （``HolidayCalendar`` 側で先勝ち採用される）。
        """
        # 会社休日は CSV ではなくコードに直書きされた ``COMPANY_HOLIDAYS`` /
        # ``COMPANY_HOLIDAYS_EXTRA`` から組み立てる（外部 I/O なし）。
        # CSV ソースの ``load_cabinet_office_csv`` と違って読み取りパスは無いが、
        # 対象範囲・生成件数を debug ログへ出しておく。
        logger.debug(
            "CompanyHolidaySource.load 開始: from_year=%d, to_year=%d, 固定=%d 区分, 臨時=%d 件",
            self._from_year,
            self._to_year,
            len(COMPANY_HOLIDAYS),
            len(COMPANY_HOLIDAYS_EXTRA),
        )
        holidays: list[Holiday] = [
            Holiday(date=extra_date, name=EXTRA_HOLIDAY_NAME)
            for extra_date in COMPANY_HOLIDAYS_EXTRA
            if self._from_year <= extra_date.year <= self._to_year
        ]
        for year in range(self._from_year, self._to_year + 1):
            for name, month_days in COMPANY_HOLIDAYS.items():
                for month, day in month_days:
                    holidays.append(Holiday(date=_dt.date(year, month, day), name=name))
        result = sorted(holidays, key=lambda h: h.date)
        logger.debug("CompanyHolidaySource.load 完了: %d 件", len(result))
        return result


__all__ = [
    "COMPANY_HOLIDAYS",
    "COMPANY_HOLIDAYS_EXTRA",
    "CompanyHolidaySource",
    "DEFAULT_YEARS_BACK",
    "DEFAULT_YEARS_AHEAD",
    "EXTRA_HOLIDAY_NAME",
]
