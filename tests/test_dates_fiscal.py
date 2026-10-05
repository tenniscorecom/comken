"""comken.core.dates の年度のテスト。

`comken/core/dates/_fiscal.py`（`fiscal_year` / `FISCAL_YEAR_START_MONTH`）の
境界を検証する。営業日判定本体（`_holidays.py`）は
`tests/test_holidays.py` で別途検証する。
"""

import datetime as _dt

from comken.core.dates import fiscal_year
from comken.core.dates._fiscal import FISCAL_YEAR_START_MONTH

# ── fiscal_year ─────────────────────────────────────────────────────────


class TestFiscalYear:
    """``fiscal_year`` の境界（4 月始まりの判定）。"""

    def test_april_first_is_new_fiscal_year(self) -> None:
        """4 月 1 日は新しい年度の 1 日目（=その年）。"""
        assert fiscal_year(_dt.date(2026, 4, 1)) == 2026

    def test_march_31_is_still_previous_fiscal_year(self) -> None:
        """3 月 31 日は前の年度の最終日（=前年）。"""
        assert fiscal_year(_dt.date(2026, 3, 31)) == 2025

    def test_january_1_is_previous_fiscal_year(self) -> None:
        """1 月 1 日は前の年度（4 月始まりのため）。"""
        assert fiscal_year(_dt.date(2026, 1, 1)) == 2025

    def test_december_31_is_same_year(self) -> None:
        """12 月 31 日はその年（年度末）。"""
        assert fiscal_year(_dt.date(2026, 12, 31)) == 2026

    def test_datetime_input_uses_date_part(self) -> None:
        """``datetime.datetime`` を渡しても日付部分で判定する。

        戻り値は ``date`` なので tzinfo の有無は結果に影響しない。
        テストはあえて tz 無し datetime を渡して「``date()`` 経由で
        動いている」ことを確かめる。
        """
        # 時刻がいくらでも、日付で 4 月 1 日ならその年
        assert fiscal_year(_dt.datetime(2026, 4, 1, 0, 0, 0)) == 2026  # noqa: DTZ001
        assert fiscal_year(_dt.datetime(2026, 4, 1, 23, 59, 59)) == 2026  # noqa: DTZ001
        # 時刻がいくらでも、日付で 3 月 31 日なら前年
        assert fiscal_year(_dt.datetime(2026, 3, 31, 23, 59, 59)) == 2025  # noqa: DTZ001

    def test_year_over_year(self) -> None:
        """1 月 1 日〜 3 月 31 日までは前年。"""
        assert fiscal_year(_dt.date(2027, 1, 1)) == 2026
        assert fiscal_year(_dt.date(2027, 2, 28)) == 2026
        assert fiscal_year(_dt.date(2027, 3, 31)) == 2026


class TestFiscalYearConstant:
    """``FISCAL_YEAR_START_MONTH`` の値は 4（4 月始まり）。"""

    def test_value_is_four(self) -> None:
        """既定の 4 月始まりはコードに固定。"""
        assert FISCAL_YEAR_START_MONTH == 4
