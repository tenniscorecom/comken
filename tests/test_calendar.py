"""comken.core.calendar のテスト。

会社用カレンダー CSV（``company_calendar.csv``）を読んで国民の祝日＋会社休日
を判定する実行時 API の挙動を検証する。生成ツール（``tools/build_calendar.py``）
側の内閣府 CSV 解析・会社休日ルールの展開は ``tests/test_build_calendar.py``
で検証する。
"""

from __future__ import annotations

import datetime as _dt
import logging
from pathlib import Path

import pytest

from comken.core.calendar import (
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
)
from comken.core.calendar._calendar import _Calendar, _set_calendar_for_test
from comken.exceptions import (
    BusinessDayNotFoundError,
    CalendarError,
    CalendarFormatError,
)

# ── 公開関数の基本動作 ──────────────────────────────────────────────────


class TestIsHoliday:
    """``is_holiday`` の挙動（国民の祝日＋会社休日を判定）。"""

    def test_new_years_day_is_holiday(self) -> None:
        """元日は国民の祝日扱い。"""
        assert is_holiday(_dt.date(2026, 1, 1)) is True

    def test_normal_weekday_is_not_holiday(self) -> None:
        """祝日でも会社休日でもなければ False。"""
        # 2024/1/9 は火曜で国民の祝日でも会社休日でもない
        assert is_holiday(_dt.date(2024, 1, 9)) is False

    def test_year_end_new_year_is_company_holiday(self) -> None:
        """12/29 - 1/3 は会社休日扱い（既定）。"""
        assert is_holiday(_dt.date(2026, 12, 29)) is True
        assert is_holiday(_dt.date(2026, 12, 30)) is True
        assert is_holiday(_dt.date(2026, 12, 31)) is True
        assert is_holiday(_dt.date(2027, 1, 1)) is True
        assert is_holiday(_dt.date(2027, 1, 2)) is True
        assert is_holiday(_dt.date(2027, 1, 3)) is True

    def test_no_holidays_outside_calendar_range(self) -> None:
        """会社用カレンダー CSV の収録範囲の外には、国民の祝日も会社休日も付かない。

        範囲外（2028 年以降、1950 年以前）は国民の祝日も会社休日も付かない。
        範囲内では年末年始休暇がそのまま休みになる。
        """
        # 2027 年までは内閣府 CSV 収録範囲内 → 12/29 - 1/3 は休み
        assert is_holiday(_dt.date(2027, 12, 31)) is True
        # 2028 年は内閣府 CSV の範囲外 → 国民の祝日も会社休日も付かない
        assert is_holiday(_dt.date(2028, 1, 2)) is False
        assert is_holiday(_dt.date(2028, 12, 31)) is False
        # 過去（1950 年）も内閣府 CSV の範囲外 → 国民の祝日も会社休日も付かない
        assert is_holiday(_dt.date(1950, 1, 2)) is False
        assert is_holiday(_dt.date(1950, 12, 31)) is False

    def test_national_holiday_wins_over_company_holiday(self) -> None:
        """国民の祝日と会社休日に重なった日は国民の祝日が優先（先勝ち）。

        2026/1/1 は元日（国民の祝日）かつ年末年始休暇（会社休日）。
        どちらも True だが、名前は「元日」が返る（生成ツールが国民の祝日を
        先勝ちで 1 行に焼き込んでいる）。
        """
        assert is_holiday(_dt.date(2026, 1, 1)) is True
        assert holiday_name(_dt.date(2026, 1, 1)) == "元日"


class TestHolidayName:
    """``holiday_name`` の挙動。"""

    def test_returns_name_on_holiday(self) -> None:
        """国民の祝日ならその名前。"""
        assert holiday_name(_dt.date(2026, 5, 4)) == "みどりの日"

    def test_returns_none_on_non_holiday(self) -> None:
        """祝日でも会社休日でもなければ None。"""
        assert holiday_name(_dt.date(2024, 1, 9)) is None

    def test_returns_company_holiday_name_on_company_holiday(self) -> None:
        """会社休日に当たれば会社休日名を返す。"""
        # 国民の祝日と重ならない会社休日は 12/30 など
        assert holiday_name(_dt.date(2026, 12, 30)) == "年末年始休暇"
        # 国民の祝日と重なる会社休日は国民の祝日が先勝ち
        assert holiday_name(_dt.date(2026, 1, 1)) == "元日"


class TestIsBusinessDay:
    """``is_business_day`` の挙動（週末スキップ・週末スキップなし）。"""

    def test_weekday_non_holiday_is_business_day(self) -> None:
        """祝日でない月曜は営業日。"""
        assert is_business_day(_dt.date(2024, 1, 9)) is True  # 火曜、祝日でも会社休日でもない

    def test_weekday_holiday_is_not_business_day(self) -> None:
        """祝日の月曜は営業日ではない。"""
        assert is_business_day(_dt.date(2024, 1, 1)) is False

    def test_saturday_is_skipped_by_default(self) -> None:
        """土曜は ``skip_weekends=True``（既定）で休業。"""
        assert is_business_day(_dt.date(2024, 1, 6)) is False  # 土曜

    def test_sunday_is_skipped_by_default(self) -> None:
        """日曜は ``skip_weekends=True``（既定）で休業。"""
        assert is_business_day(_dt.date(2024, 1, 7)) is False  # 日曜

    def test_saturday_is_business_when_skip_weekends_false(self) -> None:
        """``skip_weekends=False`` なら土曜でも祝日でなければ営業日。"""
        assert is_business_day(_dt.date(2024, 1, 6), skip_weekends=False) is True

    def test_holiday_saturday_still_not_business(self) -> None:
        """土曜でも暦なら ``False``（``skip_weekends=False`` でも）。"""
        # 2024-05-04 は土曜かつ祝日（みどりの日）
        assert is_business_day(_dt.date(2024, 5, 4), skip_weekends=False) is False

    def test_is_holiday_includes_company_holidays(self) -> None:
        """既定カレンダーには会社休日（年末年始休暇）が含まれる。

        既定の遅延生成カレンダーだけで ``is_business_day(2026/12/29)`` が
        ``False`` になることを確認する。
        """
        assert is_business_day(_dt.date(2026, 12, 29)) is False
        assert is_business_day(_dt.date(2027, 1, 3)) is False

    def test_is_business_day_uses_implicit_calendar(self) -> None:
        """``is_business_day`` が既定カレンダーをそのまま使う。

        既定カレンダーが 2026/5/3 と 2026/5/6 を祝日扱いするかをチェック
        （2026/5/3 は日曜・憲法記念日、5/6 は水曜・振替休日）。
        """
        assert is_business_day(_dt.date(2026, 5, 3)) is False
        assert is_business_day(_dt.date(2026, 5, 6)) is False
        assert is_business_day(_dt.date(2026, 5, 7)) is True  # 木、平日


class TestBusinessDayAfter:
    """``business_day_after`` の挙動。"""

    def test_skips_weekend_and_holiday(self) -> None:
        """週末と祝日の両方を飛ばす。"""
        # 2024-05-02 は木曜 → 翌営業は 2024-05-07（火）= 5/3,4,5,6 を飛ばす
        assert business_day_after(_dt.date(2024, 5, 2)) == _dt.date(2024, 5, 7)

    def test_skips_only_holiday_when_target_is_weekday(self) -> None:
        """``target`` が平日のとき、祝日だけ飛ばす。"""
        # 2024-04-30 は火曜 → 4/29 が昭和の日（祝）で、5/1 は祝日ではないので 5/1 が翌営業
        assert business_day_after(_dt.date(2024, 4, 30)) == _dt.date(2024, 5, 1)

    def test_business_day_after_respects_skip_weekends_flag(self) -> None:
        """``skip_weekends=False`` でも翌日が祝日なら飛ばす。"""
        # 2024-04-30 は火曜で国民の祝日でも会社休日でもない → 翌営業は 5/1 (水)
        assert business_day_after(_dt.date(2024, 4, 30), skip_weekends=False) == _dt.date(
            2024, 5, 1
        )
        # 2024-04-29 は昭和の日（月曜・国民の祝日）→ skip_weekends=False で翌営業は 4/30
        assert business_day_after(_dt.date(2024, 4, 29), skip_weekends=False) == _dt.date(
            2024, 4, 30
        )

    def test_target_is_business_day_returns_next_one(self) -> None:
        """``target`` が営業日でも翌営業日を返す（自身を含まない）。"""
        # 2024-05-02 (木) は営業日 → 翌営業は 2024-05-07 (火)
        assert business_day_after(_dt.date(2024, 5, 2)) == _dt.date(2024, 5, 7)


# ── 期限切れ警告 ──────────────────────────────────────────────────────────


def _holiday_calendar(holidays: dict[_dt.date, str]) -> _Calendar:
    """テスト用の ``_Calendar`` を ``{日付: 名称}`` の dict から組み立てるヘルパー。"""
    return _Calendar(holidays)


class TestExpiry:
    """``last_known_date`` / ``days_until_expiry`` の挙動。"""

    def test_last_known_date_is_max(self) -> None:
        """``last_known_date`` は収録済み祝日のうち最新の日付。"""
        cal = _holiday_calendar(
            {
                _dt.date(2026, 5, 5): "こどもの日",
                _dt.date(2026, 11, 3): "文化の日",
                _dt.date(2026, 7, 20): "海の日",
            }
        )
        assert cal.last_known_date() == _dt.date(2026, 11, 3)

    def test_days_until_expiry_positive(self) -> None:
        """未来の日付を引くと正の日数。"""
        cal = _holiday_calendar({_dt.date(2024, 12, 31): "年末"})
        assert cal.days_until_expiry(_dt.date(2024, 1, 1)) == 365

    def test_empty_calendar_is_expired(self) -> None:
        """祝日が 1件も無いときは「最初から期限切れ」扱い。"""
        empty = _Calendar({})
        assert empty.last_known_date() is None
        assert empty.days_until_expiry(_dt.date(2024, 1, 1)) == -1


class TestExpiringWarning:
    """期限切れ警告（30日切ったら 1度だけ WARNING）の挙動。"""

    def test_warning_logged_once_when_within_30_days(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """残り 30 日未満のとき WARNING が出る（同じ日で 1度だけ）。"""
        _set_calendar_for_test(_holiday_calendar({_dt.date(2024, 5, 5): "こどもの日"}))
        try:
            today = _dt.date(2024, 4, 20)  # 残り 15 日
            with caplog.at_level(logging.WARNING, logger="comken.core.calendar._calendar"):
                is_business_day(today)
                is_business_day(today)  # 2回呼んでも 1度だけ
            warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
            assert len(warnings) == 1
            assert "15" in warnings[0].getMessage()
        finally:
            _set_calendar_for_test(None)

    def test_warning_not_logged_when_far_from_expiry(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """30日以上先なら警告は出ない。"""
        _set_calendar_for_test(_holiday_calendar({_dt.date(2025, 5, 5): "こどもの日"}))
        try:
            today = _dt.date(2024, 1, 1)
            with caplog.at_level(logging.WARNING, logger="comken.core.calendar._calendar"):
                is_business_day(today)
            assert not [r for r in caplog.records if r.levelno == logging.WARNING]
        finally:
            _set_calendar_for_test(None)

    def test_warning_not_repeated_on_next_day(self, caplog: pytest.LogCaptureFixture) -> None:
        """翌日にもう一度 ``is_business_day`` を呼ぶと、その日では 1度だけ出る。"""
        _set_calendar_for_test(_holiday_calendar({_dt.date(2024, 5, 5): "こどもの日"}))
        try:
            with caplog.at_level(logging.WARNING, logger="comken.core.calendar._calendar"):
                is_business_day(_dt.date(2024, 4, 20))
                is_business_day(_dt.date(2024, 4, 21))
                is_business_day(_dt.date(2024, 4, 21))
            warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
            assert len(warnings) == 2
        finally:
            _set_calendar_for_test(None)

    def test_warning_logged_once_when_querying_after_last_known_date(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """収録最終日より後の日付を問い合わせると、範囲外 WARNING が 1度だけ出る。"""
        _set_calendar_for_test(_holiday_calendar({_dt.date(2024, 5, 5): "こどもの日"}))
        try:
            after = _dt.date(2025, 1, 1)  # 最終収録日 5/5 より後
            with caplog.at_level(logging.WARNING, logger="comken.core.calendar._calendar"):
                is_business_day(after)
                is_business_day(after)  # 同じ日の 2回目以降は増えない
                is_business_day(after + _dt.timedelta(days=10))  # 範囲外でも別の日でも増えない
            warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
            assert len(warnings) == 1
            assert "収録範囲外" in warnings[0].getMessage()
            assert str(after) in warnings[0].getMessage()
        finally:
            _set_calendar_for_test(None)

    def test_no_out_of_range_warning_when_target_is_on_or_before_last_known_date(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """最終日以前の日付では範囲外警告は出ない（期限切れ警告だけ）。"""
        # 最終収録日を十分に先に置き、範囲外にも期限切れ警告にも該当させない
        _set_calendar_for_test(_holiday_calendar({_dt.date(2025, 12, 31): "年末"}))
        try:
            with caplog.at_level(logging.WARNING, logger="comken.core.calendar._calendar"):
                is_business_day(_dt.date(2024, 1, 1))
                is_business_day(_dt.date(2025, 6, 1))
            warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
            assert not [w for w in warnings if "収録範囲外" in w.getMessage()]
        finally:
            _set_calendar_for_test(None)


# ── 例外の型階層 ──────────────────────────────────────────────────────────


class TestExceptionHierarchy:
    """個別例外が ``CalendarError`` の下にまとまっているか。"""

    @pytest.mark.parametrize(
        ("exception", "expected_name"),
        [
            (CalendarFormatError(Path("dummy.csv"), "dummy"), "CalendarFormatError"),
        ],
    )
    def test_isinstance_of_base(self, exception: CalendarError, expected_name: str) -> None:
        """全ての個別例外が ``CalendarError`` および ``ComkenError`` の派生。"""
        assert isinstance(exception, CalendarError)
        assert isinstance(exception, Exception)
        assert type(exception).__name__ == expected_name


# ── 営業日オフセット計算 ──────────────────────────────────────────────


class TestBusinessDayOffsets:
    """``business_day_after`` / ``business_day_before`` /
    ``business_day_on_or_after`` / ``business_day_on_or_before`` の挙動。
    """

    def test_after_excludes_target(self) -> None:
        """``business_day_after`` は ``target`` 自身を含まない（営業日でも翌日）。"""
        _set_calendar_for_test(_Calendar({}))
        try:
            # 2024-05-06 は月曜で営業日 → business_day_after は 5/7 火
            assert business_day_after(_dt.date(2024, 5, 6)) == _dt.date(2024, 5, 7)
        finally:
            _set_calendar_for_test(None)

    def test_on_or_after_includes_target(self) -> None:
        """``business_day_on_or_after`` は ``target`` が営業日ならそのまま返す。"""
        _set_calendar_for_test(_Calendar({}))
        try:
            assert business_day_on_or_after(_dt.date(2024, 5, 6)) == _dt.date(2024, 5, 6)
        finally:
            _set_calendar_for_test(None)

    def test_after_vs_on_or_after_when_target_is_business_day(self) -> None:
        """営業日を渡したとき、前者は翌日・後者はその日自身を返す。"""
        _set_calendar_for_test(_Calendar({}))
        try:
            d = _dt.date(2024, 5, 6)  # 月曜・営業日
            assert business_day_after(d) == _dt.date(2024, 5, 7)
            assert business_day_on_or_after(d) == _dt.date(2024, 5, 6)
        finally:
            _set_calendar_for_test(None)

    def test_before_excludes_target(self) -> None:
        """``business_day_before`` は ``target`` 自身を含まない（営業日でも前日）。"""
        _set_calendar_for_test(_Calendar({}))
        try:
            assert business_day_before(_dt.date(2024, 5, 6)) == _dt.date(2024, 5, 3)
        finally:
            _set_calendar_for_test(None)

    def test_on_or_before_includes_target(self) -> None:
        """``business_day_on_or_before`` は ``target`` が営業日ならそのまま返す。"""
        _set_calendar_for_test(_Calendar({}))
        try:
            assert business_day_on_or_before(_dt.date(2024, 5, 6)) == _dt.date(2024, 5, 6)
        finally:
            _set_calendar_for_test(None)

    def test_on_or_after_skips_holiday(self) -> None:
        """``target`` が祝日のとき、``on_or_after`` は翌日以降を探す。"""
        _set_calendar_for_test(_holiday_calendar({_dt.date(2024, 5, 6): "架空の祝日"}))
        try:
            assert business_day_on_or_after(_dt.date(2024, 5, 6)) == _dt.date(2024, 5, 7)
        finally:
            _set_calendar_for_test(None)


class TestNthBusinessDayOfMonth:
    """``nth_business_day_of_month`` の挙動（祝土日をまたぐ月で検証）。"""

    def test_returns_nth_business_day(self) -> None:
        """月の第 ``n`` 営業日を返す。"""
        _set_calendar_for_test(_Calendar({}))
        try:
            assert nth_business_day_of_month(_dt.date(2024, 5, 15), 3) == _dt.date(2024, 5, 3)
        finally:
            _set_calendar_for_test(None)

    def test_returns_nth_business_day_skipping_holidays(self) -> None:
        """祝土日をまたぐ月の第 ``n`` 営業日を返す。"""
        _set_calendar_for_test(
            _holiday_calendar(
                {
                    _dt.date(2024, 5, 3): "憲法",
                    _dt.date(2024, 5, 4): "みどり",
                    _dt.date(2024, 5, 5): "こどもの日",
                    _dt.date(2024, 5, 6): "振替",
                }
            )
        )
        try:
            assert nth_business_day_of_month(_dt.date(2024, 5, 15), 3) == _dt.date(2024, 5, 7)
        finally:
            _set_calendar_for_test(None)

    def test_returns_first_business_day(self) -> None:
        """``n == 1`` でその月の最初の営業日を返す。"""
        _set_calendar_for_test(_Calendar({}))
        try:
            assert nth_business_day_of_month(_dt.date(2024, 5, 15), 1) == _dt.date(2024, 5, 1)
        finally:
            _set_calendar_for_test(None)

    def test_raises_when_n_exceeds_month_business_days(self) -> None:
        """``n`` が月の営業日数を超えると ``BusinessDayNotFoundError``。"""
        march = {_dt.date(2024, 3, d): f"holiday{d}" for d in range(1, 32)}
        _set_calendar_for_test(_Calendar(march))
        try:
            with pytest.raises(BusinessDayNotFoundError):
                nth_business_day_of_month(_dt.date(2024, 3, 15), 1)
        finally:
            _set_calendar_for_test(None)

    def test_raises_when_n_is_less_than_one(self) -> None:
        """``n < 1`` で ``BusinessDayNotFoundError``。"""
        _set_calendar_for_test(_Calendar({}))
        try:
            with pytest.raises(BusinessDayNotFoundError):
                nth_business_day_of_month(_dt.date(2024, 5, 15), 0)
            with pytest.raises(BusinessDayNotFoundError):
                nth_business_day_of_month(_dt.date(2024, 5, 15), -1)
        finally:
            _set_calendar_for_test(None)


class TestFirstAndLastBusinessDayOfMonth:
    """``first_business_day_of_month`` / ``last_business_day_of_month`` の挙動。"""

    def test_last_business_day_when_month_end_is_weekend(self) -> None:
        """月末が土日のとき、直前の営業日に遡る。"""
        _set_calendar_for_test(_Calendar({}))
        try:
            assert last_business_day_of_month(_dt.date(2024, 8, 20)) == _dt.date(2024, 8, 30)
        finally:
            _set_calendar_for_test(None)

    def test_last_business_day_when_month_end_is_sunday(self) -> None:
        """月末が日曜のとき、金曜に戻る。"""
        _set_calendar_for_test(_Calendar({}))
        try:
            assert last_business_day_of_month(_dt.date(2024, 6, 15)) == _dt.date(2024, 6, 28)
        finally:
            _set_calendar_for_test(None)

    def test_last_business_day_when_month_end_is_holiday(self) -> None:
        """月末が祝日のとき、直前の営業日に遡る。"""
        _set_calendar_for_test(_holiday_calendar({_dt.date(2024, 4, 30): "月末祝日"}))
        try:
            assert last_business_day_of_month(_dt.date(2024, 4, 15)) == _dt.date(2024, 4, 29)
        finally:
            _set_calendar_for_test(None)

    def test_first_business_day_when_month_start_is_weekend(self) -> None:
        """月初が土日のとき、最初の営業日に進む。"""
        _set_calendar_for_test(_Calendar({}))
        try:
            assert first_business_day_of_month(_dt.date(2024, 9, 15)) == _dt.date(2024, 9, 2)
        finally:
            _set_calendar_for_test(None)

    def test_month_with_no_business_days_raises(self) -> None:
        """前後に ``BUSINESS_DAY_SEARCH_LIMIT`` を超える祝日がある月では例外。"""
        span_days = (_dt.date(2025, 12, 31) - _dt.date(2023, 1, 1)).days + 1
        assert span_days > BUSINESS_DAY_SEARCH_LIMIT * 2
        long_holidays = {
            _dt.date(2023, 1, 1) + _dt.timedelta(days=i): f"h{i}" for i in range(span_days)
        }
        _set_calendar_for_test(_Calendar(long_holidays))
        try:
            with pytest.raises(BusinessDayNotFoundError):
                first_business_day_of_month(_dt.date(2024, 3, 15))
            with pytest.raises(BusinessDayNotFoundError):
                last_business_day_of_month(_dt.date(2024, 3, 15))
        finally:
            _set_calendar_for_test(None)


class TestAddBusinessDays:
    """``add_business_days`` の挙動。"""

    def test_zero_returns_target_unchanged(self) -> None:
        """``n == 0`` は ``target`` をそのまま返す（休日でも）。"""
        _set_calendar_for_test(_holiday_calendar({_dt.date(2024, 1, 1): "元日"}))
        try:
            holiday_target = _dt.date(2024, 1, 1)
            assert add_business_days(holiday_target, 0) == holiday_target
        finally:
            _set_calendar_for_test(None)

    def test_positive_one_returns_business_day_after_target(self) -> None:
        """``n == 1`` で ``target`` が営業日でも**翌営業日**を返す（Excel WORKDAY 互換）。"""
        # 年末年始休暇の影響を受けない 2024/2 を使う
        _set_calendar_for_test(_holiday_calendar({_dt.date(2024, 2, 11): "建国記念"}))
        try:
            # 2024-02-13 (火) は祝日ではない営業日 + 1 営業日 → 2/14 (水)
            assert add_business_days(_dt.date(2024, 2, 13), 1) == _dt.date(2024, 2, 14)
        finally:
            _set_calendar_for_test(None)

    def test_positive_skips_weekend_and_holiday(self) -> None:
        """``n > 0`` で営業日単位に進む。"""
        _set_calendar_for_test(_holiday_calendar({_dt.date(2024, 2, 11): "建国記念"}))
        try:
            # 2024-02-13 (火) + 1 営業日 → 2/14 (水)
            assert add_business_days(_dt.date(2024, 2, 13), 1) == _dt.date(2024, 2, 14)
            # 2 営業日 → 2/15 (木)
            assert add_business_days(_dt.date(2024, 2, 13), 2) == _dt.date(2024, 2, 15)
        finally:
            _set_calendar_for_test(None)

    def test_negative_returns_previous_business_days(self) -> None:
        """``n < 0`` で ``|n|`` 営業日前に戻る。"""
        _set_calendar_for_test(_holiday_calendar({_dt.date(2024, 2, 11): "建国記念"}))
        try:
            # 2024-02-14 (水) -1 → 2/13 (火)
            assert add_business_days(_dt.date(2024, 2, 14), -1) == _dt.date(2024, 2, 13)
            # -2 → 2/12 (月)
            assert add_business_days(_dt.date(2024, 2, 14), -2) == _dt.date(2024, 2, 12)
        finally:
            _set_calendar_for_test(None)


class TestBusinessDaySearchLimit:
    """探索上限に達すると ``BusinessDayNotFoundError`` になることを確認。"""

    def test_raises_after_search_limit_when_all_days_are_holidays(self) -> None:
        """全日が祝日のカレンダーで ``business_day_after`` が上限到達で例外。"""
        holidays = {
            _dt.date(2025, 1, 1) + _dt.timedelta(days=i): "h"
            for i in range(BUSINESS_DAY_SEARCH_LIMIT + 100)
        }
        _set_calendar_for_test(_Calendar(holidays))
        try:
            with pytest.raises(BusinessDayNotFoundError):
                business_day_after(_dt.date(2025, 1, 1))
        finally:
            _set_calendar_for_test(None)


# ── 期間計算（既定カレンダー使用） ──────────────────────────────────────


class TestCalendarBoundOn2026May:
    """2026 年 5 月（GW を含む月）での business_day_after / on_or_after の対比。"""

    def test_business_day_after_from_may_3(self) -> None:
        """``business_day_after(2026/5/3)`` は 5/7 を返す（5/3 自身は含まない）。"""
        assert business_day_after(_dt.date(2026, 5, 3)) == _dt.date(2026, 5, 7)

    def test_business_day_on_or_after_from_may_3(self) -> None:
        """``business_day_on_or_after(2026/5/3)`` は GW 後の 5/7 を返す。"""
        assert business_day_on_or_after(_dt.date(2026, 5, 3)) == _dt.date(2026, 5, 7)

    def test_business_day_after_from_weekday_uses_next(self) -> None:
        """``business_day_after(2026/5/1 金曜)`` は 5/7 木曜。"""
        assert business_day_after(_dt.date(2026, 5, 1)) == _dt.date(2026, 5, 7)

    def test_business_day_on_or_after_from_weekday_returns_target(self) -> None:
        """``business_day_on_or_after(2026/5/1 金曜)`` は 5/1 そのものを返す。"""
        assert business_day_on_or_after(_dt.date(2026, 5, 1)) == _dt.date(2026, 5, 1)

    def test_business_day_on_or_before_15th(self) -> None:
        """「15日、休みならその前の営業日」の例（``business_day_on_or_before``）。"""
        assert business_day_on_or_before(_dt.date(2026, 5, 15)) == _dt.date(2026, 5, 15)
        assert business_day_on_or_before(_dt.date(2026, 5, 16)) == _dt.date(2026, 5, 15)


class TestModuleFunctionsFromCore:
    """``comken.core`` から再エクスポートされた同名関数の挙動。"""

    def test_core_reexports_match_calendar_module(self) -> None:
        """``comken.core`` から ``is_business_day`` などを取って既定カレンダーで動く。"""
        from comken.core import is_business_day as core_is_business_day
        from comken.core import last_business_day_of_month as core_last
        from comken.core import nth_business_day_of_month as core_nth

        assert core_is_business_day(_dt.date(2026, 5, 3)) is False
        assert core_last(_dt.date(2026, 5, 1)) == _dt.date(2026, 5, 29)
        assert core_nth(_dt.date(2026, 5, 1), 3) == _dt.date(2026, 5, 8)


class TestClockMonthHelpers:
    """``month_start`` / ``month_end`` の挙動（``comken.core.clock``）。"""

    def test_month_start_returns_first_day(self) -> None:
        """``month_start(d)`` はその月の 1 日を返す。"""
        from comken.core.clock import month_start

        assert month_start(_dt.date(2026, 5, 15)) == _dt.date(2026, 5, 1)
        assert month_start(_dt.date(2024, 2, 29)) == _dt.date(2024, 2, 1)

    def test_month_end_handles_28_29_30_31(self) -> None:
        """``month_end`` は月の日数（28/29/30/31）を正しく扱う。"""
        from comken.core.clock import month_end

        assert month_end(_dt.date(2026, 5, 15)) == _dt.date(2026, 5, 31)
        assert month_end(_dt.date(2026, 4, 15)) == _dt.date(2026, 4, 30)
        assert month_end(_dt.date(2024, 2, 15)) == _dt.date(2024, 2, 29)
        assert month_end(_dt.date(2025, 2, 15)) == _dt.date(2025, 2, 28)


# ── CSV 読み込みエラー ──────────────────────────────────────────────


class TestCompanyCalendarCsvFormatError:
    """``company_calendar.csv`` の形式エラー時の挙動。"""

    def test_missing_file_raises_format_error(self, tmp_path: Path) -> None:
        """ファイルが無ければ ``CalendarFormatError``。"""
        with pytest.raises(CalendarFormatError):
            _Calendar.load(tmp_path / "nope.csv")

    def test_wrong_header_raises_format_error(self, tmp_path: Path) -> None:
        """ヘッダーが ``date,name`` でないと ``CalendarFormatError``。"""
        bad = tmp_path / "bad.csv"
        bad.write_text(
            "col1,col2\n2024-01-01,元日\n",
            encoding="utf-8-sig",
        )
        with pytest.raises(CalendarFormatError):
            _Calendar.load(bad)

    def test_bad_date_raises_format_error(self, tmp_path: Path) -> None:
        """日付が解釈できない行があると ``CalendarFormatError``。"""
        bad = tmp_path / "bad.csv"
        bad.write_text(
            "date,name\nhello,元日\n",
            encoding="utf-8-sig",
        )
        with pytest.raises(CalendarFormatError):
            _Calendar.load(bad)

    def test_empty_after_header_raises_format_error(self, tmp_path: Path) -> None:
        """データ行が無ければ ``CalendarFormatError``。"""
        bad = tmp_path / "bad.csv"
        bad.write_text("date,name\n", encoding="utf-8-sig")
        with pytest.raises(CalendarFormatError):
            _Calendar.load(bad)


# ── モジュール・定数 ──────────────────────────────────────────────────────


class TestModuleConstants:
    """公開定数の形と値のチェック。"""

    def test_business_day_search_limit_is_30(self) -> None:
        """``BUSINESS_DAY_SEARCH_LIMIT`` は 30（休日広範囲時の無限ループ防止）。"""
        assert BUSINESS_DAY_SEARCH_LIMIT == 30

    def test_expiring_warning_days_is_30(self) -> None:
        """``EXPIRING_WARNING_DAYS`` は 30（期限切れ検知の閾値）。"""
        assert EXPIRING_WARNING_DAYS == 30

    def test_calendar_csv_path_points_to_data_folder(self) -> None:
        """``CALENDAR_CSV_PATH`` は data/company_calendar.csv。"""
        assert CALENDAR_CSV_PATH.name == "company_calendar.csv"
        assert CALENDAR_CSV_PATH.parent.name == "data"
