"""comken.core.dates の年度・yyyymmdd 変換のテスト。

`comken/core/dates/_fiscal.py`（`fiscal_year` / `FISCAL_YEAR_START_MONTH`）と
`comken/core/dates/_format.py`（`format_yyyymmdd` / `parse_yyyymmdd`）の
境界・例外仕様を検証する。営業日判定本体（`_holidays.py`）は
`tests/test_holidays.py` で別途検証する。
"""

import datetime as _dt

import pytest

from comken.core.dates import (
    FISCAL_YEAR_START_MONTH,
    fiscal_year,
    format_yyyymmdd,
    parse_yyyymmdd,
)
from comken.exceptions import DateFormatError

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


# ── format_yyyymmdd ─────────────────────────────────────────────────────


class TestFormatYyyymmdd:
    """``format_yyyymmdd``（date → 8 桁数字列）。"""

    def test_zero_pads_single_digit_month_and_day(self) -> None:
        """1 桁の月日もゼロ埋めする。"""
        assert format_yyyymmdd(_dt.date(2026, 1, 5)) == "20260105"
        assert format_yyyymmdd(_dt.date(2026, 10, 5)) == "20261005"

    def test_accepts_datetime(self) -> None:
        """``datetime.datetime`` を渡しても日付部分だけで変換する（時刻は捨てる）。"""
        assert format_yyyymmdd(_dt.datetime(2026, 10, 5, 12, 30, 45)) == "20261005"  # noqa: DTZ001

    def test_leap_day(self) -> None:
        """閏日（2/29）もそのまま 8 桁で返す。"""
        assert format_yyyymmdd(_dt.date(2024, 2, 29)) == "20240229"


# ── parse_yyyymmdd ──────────────────────────────────────────────────────


class TestParseYyyymmdd:
    """``parse_yyyymmdd``（8 桁数字列 → date）。"""

    def test_valid_input(self) -> None:
        """正常な 8 桁数字列を変換する。"""
        assert parse_yyyymmdd("20261005") == _dt.date(2026, 10, 5)

    def test_strips_surrounding_whitespace(self) -> None:
        """前後の空白は ``strip`` で除去してから判定する。"""
        assert parse_yyyymmdd("  20261005  ") == _dt.date(2026, 10, 5)
        assert parse_yyyymmdd("\t20261005\n") == _dt.date(2026, 10, 5)

    def test_leap_day_2024(self) -> None:
        """閏日（2024/2/29）は通る。"""
        assert parse_yyyymmdd("20240229") == _dt.date(2024, 2, 29)

    @pytest.mark.parametrize("text", ["2026105", "202610050", "2026", "20261"])
    def test_invalid_length_raises(self, text: str) -> None:
        """桁数が合わない（7 桁・9 桁・短い）は ``DateFormatError``。"""
        with pytest.raises(DateFormatError, match="yyyymmdd 形式ではありません"):
            parse_yyyymmdd(text)

    def test_separator_raises(self) -> None:
        """区切り文字付き（``2026-10-05``）は ``DateFormatError``。"""
        with pytest.raises(DateFormatError, match="yyyymmdd 形式ではありません"):
            parse_yyyymmdd("2026-10-05")

    def test_slash_separator_raises(self) -> None:
        """スラッシュ区切り（``2026/10/05``）も ``DateFormatError``。"""
        with pytest.raises(DateFormatError, match="yyyymmdd 形式ではありません"):
            parse_yyyymmdd("2026/10/05")

    def test_fullwidth_digits_raise(self) -> None:
        """全角数字（``２０２６１００５``）は ``DateFormatError``。"""
        with pytest.raises(DateFormatError, match="yyyymmdd 形式ではありません"):
            parse_yyyymmdd("２０２６１００５")

    def test_non_digit_raises(self) -> None:
        """数字以外（英字・記号）が混じると ``DateFormatError``。"""
        with pytest.raises(DateFormatError, match="yyyymmdd 形式ではありません"):
            parse_yyyymmdd("2026100a")
        with pytest.raises(DateFormatError, match="yyyymmdd 形式ではありません"):
            parse_yyyymmdd("2026-1005")

    def test_non_leap_day_raises(self) -> None:
        """存在しない日付（``20250229``）は ``DateFormatError``。"""
        with pytest.raises(DateFormatError, match="yyyymmdd 形式の日付として解釈できません"):
            parse_yyyymmdd("20250229")

    def test_invalid_day_raises(self) -> None:
        """存在しない日付（``20260230``）も ``DateFormatError``。"""
        with pytest.raises(DateFormatError, match="yyyymmdd 形式の日付として解釈できません"):
            parse_yyyymmdd("20260230")

    def test_invalid_month_raises(self) -> None:
        """存在しない月（``20261301``）も ``DateFormatError``。"""
        with pytest.raises(DateFormatError, match="yyyymmdd 形式の日付として解釈できません"):
            parse_yyyymmdd("20261301")

    def test_error_message_includes_original_input(self) -> None:
        """エラーメッセージに受け取った値が含まれる（デバッグしやすくする）。"""
        with pytest.raises(DateFormatError, match="2026-10-05"):
            parse_yyyymmdd("2026-10-05")


# ── 往復 ────────────────────────────────────────────────────────────────


class TestRoundTrip:
    """``format_yyyymmdd(parse_yyyymmdd(x)) == x`` / ``parse(format(d)) == d``。"""

    @pytest.mark.parametrize(
        "day",
        [
            _dt.date(2026, 1, 1),
            _dt.date(2026, 12, 31),
            _dt.date(2024, 2, 29),  # 閏日
            _dt.date(2025, 7, 15),
            _dt.date(2000, 1, 1),
            _dt.date(2099, 9, 9),
        ],
    )
    def test_round_trip_via_string(self, day: _dt.date) -> None:
        """``parse(format(d)) == d``。"""
        assert parse_yyyymmdd(format_yyyymmdd(day)) == day

    @pytest.mark.parametrize(
        "text",
        ["20260101", "20261231", "20240229", "20250715", "20000101", "20990909"],
    )
    def test_round_trip_via_date(self, text: str) -> None:
        """``format(parse(text)) == text``。"""
        assert format_yyyymmdd(parse_yyyymmdd(text)) == text
