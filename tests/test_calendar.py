"""comken.core.calendar のテスト。

内閣府の祝日 CSV（CP932 エンコード）と会社の休業日ルール、
ソース Protocol の各経路を横断的に検証する。
"""

from __future__ import annotations

import csv
import datetime as _dt
import logging
from pathlib import Path

import pytest

from comken.core.calendar import (
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
)
from comken.core.calendar._calendar import _Calendar, _set_calendar_for_test
from comken.core.calendar.company import (
    company_holiday_name,
)
from comken.core.calendar.computed import _ComputedSource
from comken.exceptions import (
    BusinessDayNotFoundError,
    CalendarError,
    CalendarFormatError,
    CalendarSourceError,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "holidays" / "syukujitsu_sample.csv"


# ── 内閣府 CSV ローダー ──────────────────────────────────────────────────


class TestCabinetOfficeCsvLoader:
    """内閣府 CSV（CP932）の読み取り。"""

    def test_loads_real_format(self) -> None:
        """fixture を CP932 で読んで Holiday に変換できる。"""
        from comken.core.calendar.csv_source import load_cabinet_office_csv

        holidays = load_cabinet_office_csv(FIXTURE_PATH)

        assert holidays, "1件以上読み取れるべき"
        # fixture 内では「元日」が 2024 / 2025 / 2026 で揃う
        dates = {h.date for h in holidays}
        assert _dt.date(2024, 1, 1) in dates
        assert _dt.date(2025, 1, 1) in dates
        assert _dt.date(2026, 1, 1) in dates
        # 名称はそのまま入る
        from comken.core.calendar._calendar import Holiday

        assert Holiday(date=_dt.date(2024, 5, 3), name="憲法記念日") in holidays
        # ヘッダー行は結果に含まれない
        assert all(h.name != "国民の祝日・休日名称" for h in holidays)

    def test_missing_file_raises_format_error(self, tmp_path: Path) -> None:
        """ファイルが無ければ ``CalendarFormatError``。"""
        from comken.core.calendar.csv_source import load_cabinet_office_csv

        missing = tmp_path / "nope.csv"
        with pytest.raises(CalendarFormatError):
            load_cabinet_office_csv(missing)

    def test_garbage_text_raises_format_error(self, tmp_path: Path) -> None:
        """日付として読めない文字列だけだと ``CalendarFormatError``。"""
        from comken.core.calendar.csv_source import load_cabinet_office_csv

        bad = tmp_path / "bad.csv"
        bad.write_text("hello,world\nfoo,bar\n", encoding="cp932")
        with pytest.raises(CalendarFormatError):
            load_cabinet_office_csv(bad)

    def test_wrong_encoding_raises_format_error(self, tmp_path: Path) -> None:
        """CP932 以外の文字コードで書かれたものは読めない（FormatError）。"""
        from comken.core.calendar.csv_source import load_cabinet_office_csv

        utf8 = tmp_path / "utf8.csv"
        # fixture をそのまま UTF-8 で書いたものを作る（CP932 と食い違う）
        utf8.write_text(
            "国民の祝日・休日月日,国民の祝日・休日名称\n2024-01-01,元日\n",
            encoding="utf-8",
        )
        with pytest.raises(CalendarFormatError):
            load_cabinet_office_csv(utf8)


# ── 公開関数の基本動作 ──────────────────────────────────────────────────


def _bundled_calendar() -> _Calendar:
    """同梱の ``syukujitsu.csv`` から組み立てた ``_Calendar``。

    テスト fixture は業務で使う範囲を抜粋した小さなものだが、
    ゴールデンウィークのように「複数日が連なって休業」するケースを
    検証するには収録範囲が足りない。``comken/core/calendar/data/syukujitsu.csv``
    には 2027 年までの完全な祝日が収録されているので、
    「実カレンダー通り」の挙動を確かめるときはこれを使う。
    """
    return _Calendar.from_csv(BUNDLED_CSV_PATH)


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

    def test_company_holiday_year_independent(self) -> None:
        """会社休日は年範囲に依存しない（実行時のルール判定）。

        範囲外だったはずの年（2028年以降、1990年以前）でも年末年始休暇は
        そのまま休みになる（国民の祝日データ期限とは独立）。
        """
        # 2028 年の年末年始
        assert is_holiday(_dt.date(2028, 1, 2)) is True
        assert is_holiday(_dt.date(2028, 12, 31)) is True
        # 過去（1990 年）の年末年始
        assert is_holiday(_dt.date(1990, 1, 2)) is True
        assert is_holiday(_dt.date(1990, 12, 31)) is True
        # もっと遠く（2090 年）
        assert is_holiday(_dt.date(2090, 12, 31)) is True

    def test_national_holiday_wins_over_company_holiday(self) -> None:
        """国民の祝日と公司休日に重なった日は国民の祝が優先（先勝ち）。

        2026/1/1 は元日（国民の祝日）かつ年末年始休暇（会社休日）。
        どちらも True だが、名前は「元日」が返る（国民の祝日が先勝ち）。
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

    def test_extra_holidays_named_company_holiday(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``COMPANY_HOLIDAYS_EXTRA`` に足した日付は「会社休業日」。"""
        monkeypatch.setattr(
            "comken.core.calendar.company.COMPANY_HOLIDAYS_EXTRA",
            (_dt.date(2026, 11, 4),),
        )
        assert holiday_name(_dt.date(2026, 11, 4)) == "会社休業日"
        # 月日の会社休日ルールはそのまま
        assert holiday_name(_dt.date(2026, 12, 29)) == "年末年始休暇"


class TestIsBusinessDay:
    """``is_business_day`` の挙動（週末スキップ・週末スキップなし）。"""

    def test_weekday_non_holiday_is_business_day(self) -> None:
        """祝日でない月曜は営業日。"""
        cal = _bundled_calendar()
        _set_calendar_for_test(cal)
        try:
            assert is_business_day(_dt.date(2024, 1, 9)) is True  # 火曜、祝日でも会社休日でもない
        finally:
            _set_calendar_for_test(None)

    def test_weekday_holiday_is_not_business_day(self) -> None:
        """祝日の月曜は営業日ではない。"""
        cal = _bundled_calendar()
        _set_calendar_for_test(cal)
        try:
            assert is_business_day(_dt.date(2024, 1, 1)) is False
        finally:
            _set_calendar_for_test(None)

    def test_saturday_is_skipped_by_default(self) -> None:
        """土曜は ``skip_weekends=True``（既定）で休業。"""
        cal = _bundled_calendar()
        _set_calendar_for_test(cal)
        try:
            assert is_business_day(_dt.date(2024, 1, 6)) is False  # 土曜
        finally:
            _set_calendar_for_test(None)

    def test_sunday_is_skipped_by_default(self) -> None:
        """日曜は ``skip_weekends=True``（既定）で休業。"""
        cal = _bundled_calendar()
        _set_calendar_for_test(cal)
        try:
            assert is_business_day(_dt.date(2024, 1, 7)) is False  # 日曜
        finally:
            _set_calendar_for_test(None)

    def test_saturday_is_business_when_skip_weekends_false(self) -> None:
        """``skip_weekends=False`` なら土曜でも祝日でなければ営業日。"""
        cal = _bundled_calendar()
        _set_calendar_for_test(cal)
        try:
            assert is_business_day(_dt.date(2024, 1, 6), skip_weekends=False) is True
        finally:
            _set_calendar_for_test(None)

    def test_holiday_saturday_still_not_business(self) -> None:
        """土曜でも日历なら ``False``（``skip_weekends=False`` でも）。"""
        cal = _bundled_calendar()
        _set_calendar_for_test(cal)
        try:
            # 2024-05-04 は土曜かつ祝日（みどりの日）
            assert is_business_day(_dt.date(2024, 5, 4), skip_weekends=False) is False
        finally:
            _set_calendar_for_test(None)

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
        _set_calendar_for_test(_bundled_calendar())
        try:
            # 2024-05-02 は木曜 → 翌営業は 2024-05-07（火）= 5/3,4,5,6 を飛ばす
            assert business_day_after(_dt.date(2024, 5, 2)) == _dt.date(2024, 5, 7)
        finally:
            _set_calendar_for_test(None)

    def test_skips_only_holiday_when_target_is_weekday(self) -> None:
        """``target`` が平日のとき、祝日だけ飛ばす。"""
        _set_calendar_for_test(_bundled_calendar())
        try:
            # 2024-04-30 は火曜 → 4/29 が昭和の日（祝）で、5/1 は祝日ではないので 5/1 が翌営業
            assert business_day_after(_dt.date(2024, 4, 30)) == _dt.date(2024, 5, 1)
        finally:
            _set_calendar_for_test(None)

    def test_business_day_after_respects_skip_weekends_flag(self) -> None:
        """``skip_weekends=False`` でも翌日が祝日なら飛ばす。"""
        _set_calendar_for_test(_bundled_calendar())
        try:
            # 2024-04-30 は火曜で国民の祝日でも会社休日でもない → 翌営業は 5/1 (水)
            assert business_day_after(_dt.date(2024, 4, 30), skip_weekends=False) == _dt.date(
                2024, 5, 1
            )
            # 2024-04-29 は昭和の日（月曜・国民の祝日）→ skip_weekends=False で翌営業は 4/30
            assert business_day_after(_dt.date(2024, 4, 29), skip_weekends=False) == _dt.date(
                2024, 4, 30
            )
        finally:
            _set_calendar_for_test(None)

    def test_target_is_business_day_returns_next_one(self) -> None:
        """``target`` が営業日でも翌営業日を返す（自身を含まない）。"""
        _set_calendar_for_test(_bundled_calendar())
        try:
            # 2024-05-02 (木) は営業日 → 翌営業は 2024-05-07 (火)
            assert business_day_after(_dt.date(2024, 5, 2)) == _dt.date(2024, 5, 7)
        finally:
            _set_calendar_for_test(None)


# ── 期限切れ警告 ──────────────────────────────────────────────────────────


class TestExpiry:
    """``expires_after`` / ``days_until_expiry`` / ``last_known_date`` の挙動。"""

    def test_last_known_date_is_max(self) -> None:
        """``last_known_date`` は収録済み祝日のうち最新の日付。"""
        # テスト用 fixture は業務で使う範囲を抜粋した小さなもの
        cal = _Calendar.from_csv(FIXTURE_PATH)
        last = cal.last_known_date()
        # fixture の最終日は 2026-11-03（文化の日）
        assert last == _dt.date(2026, 11, 3)

    def test_expires_after_true_when_past_last_known(self) -> None:
        """最終日より後の日付は期限切れ。"""
        cal = _bundled_calendar()
        last = cal.last_known_date()
        assert last is not None
        assert cal.expires_after(last + _dt.timedelta(days=1)) is True
        # 最終日当日は「収録済み」扱い（境界は is_business_day 側で注意）
        assert cal.expires_after(last) is True

    def test_expires_after_false_when_before_last_known(self) -> None:
        """最終日より前は期限切れではない。"""
        cal = _bundled_calendar()
        last = cal.last_known_date()
        assert last is not None
        assert cal.expires_after(_dt.date(2024, 1, 1)) is False

    def test_days_until_expiry_positive(self) -> None:
        """未来の日付を引くと正の日数。"""
        cal = _bundled_calendar()
        last = cal.last_known_date()
        assert last is not None
        assert cal.days_until_expiry(_dt.date(2024, 1, 1)) == (last - _dt.date(2024, 1, 1)).days

    def test_empty_calendar_is_expired(self) -> None:
        """祝日が 1件も無いときは「最初から期限切れ」扱い。"""
        empty = _Calendar([])
        assert empty.last_known_date() is None
        assert empty.expires_after(_dt.date(2024, 1, 1)) is True
        assert empty.days_until_expiry(_dt.date(2024, 1, 1)) == -1


class TestExpiringWarning:
    """期限切れ警告（30日切ったら 1度だけ WARNING）の挙動。"""

    def test_warning_logged_once_when_within_30_days(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """残り 30 日未満のとき WARNING が出る（同じ日で 1度だけ）。"""
        _set_calendar_for_test(_Calendar([_calendar_holiday(2024, 5, 5, "こどもの日")]))
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
        _set_calendar_for_test(_Calendar([_calendar_holiday(2025, 5, 5, "こどもの日")]))
        try:
            today = _dt.date(2024, 1, 1)
            with caplog.at_level(logging.WARNING, logger="comken.core.calendar._calendar"):
                is_business_day(today)
            assert not [r for r in caplog.records if r.levelno == logging.WARNING]
        finally:
            _set_calendar_for_test(None)

    def test_warning_not_repeated_on_next_day(self, caplog: pytest.LogCaptureFixture) -> None:
        """翌日にもう一度 ``is_business_day`` を呼ぶと、その日では 1度だけ出る。"""
        _set_calendar_for_test(_Calendar([_calendar_holiday(2024, 5, 5, "こどもの日")]))
        try:
            with caplog.at_level(logging.WARNING, logger="comken.core.calendar._calendar"):
                is_business_day(_dt.date(2024, 4, 20))
                is_business_day(_dt.date(2024, 4, 21))
                is_business_day(_dt.date(2024, 4, 21))
            warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
            assert len(warnings) == 2
        finally:
            _set_calendar_for_test(None)


def _calendar_holiday(year: int, month: int, day: int, name: str):
    """テスト用の ``Holiday`` を組み立てるヘルパー。"""
    from comken.core.calendar._calendar import Holiday

    return Holiday(date=_dt.date(year, month, day), name=name)


# ── _ComputedSource ──────────────────────────────────────────────


def _computed_calendar(year: int) -> dict[_dt.date, str]:
    """その年の ``{日付: 祝日名}`` を計算で作る。"""
    return {
        h.date: h.name
        for h in _ComputedSource(from_year=year, to_year=year).load()
    }


class TestComputedSource:
    """``_ComputedSource`` の出力（mokejp/holidays_jp のアルゴリズム）。"""

    def test_computed_returns_all_2026_holidays(self) -> None:
        """2026 年の国民の祝日全部を個別に assert する。

        会社休日（年末年始休暇など）は ``company.py`` 側で表現するように
        なったので、ここでは国民の祝日だけを確認する。
        """
        source = _ComputedSource(from_year=2026, to_year=2026)
        holidays = {h.date: h.name for h in source.load()}
        expected = {
            _dt.date(2026, 1, 1): "元日",
            _dt.date(2026, 1, 12): "成人の日",
            _dt.date(2026, 2, 11): "建国記念の日",
            _dt.date(2026, 3, 20): "春分の日",
            _dt.date(2026, 4, 29): "昭和の日",
            _dt.date(2026, 5, 3): "憲法記念日",
            _dt.date(2026, 5, 4): "みどりの日",
            _dt.date(2026, 5, 5): "こどもの日",
            _dt.date(2026, 7, 20): "海の日",
            _dt.date(2026, 8, 11): "山の日",
            _dt.date(2026, 9, 21): "敬老の日",
            _dt.date(2026, 9, 22): "国民の休日",
            _dt.date(2026, 9, 23): "秋分の日",
            _dt.date(2026, 10, 12): "スポーツの日",
            _dt.date(2026, 11, 3): "文化の日",
            _dt.date(2026, 11, 23): "勤労感謝の日",
        }
        for date_, name in expected.items():
            assert date_ in holidays, f"{date_} が祝日として含まれていません"
            assert holidays[date_] == name, (
                f"{date_} の名称が {holidays[date_]!r} になっています（期待: {name!r}）"
            )

    def test_computed_returns_all_2020_special_cases(self) -> None:
        """2020 年のオリンピック特例（海の日 7/23、スポーツ 7/24、山の日 8/10）。"""
        source = _ComputedSource(from_year=2020, to_year=2020)
        holidays = {h.date: h.name for h in source.load()}
        assert holidays[_dt.date(2020, 7, 23)] == "海の日"
        assert holidays[_dt.date(2020, 7, 24)] == "スポーツの日"
        assert holidays[_dt.date(2020, 8, 10)] == "山の日"
        # 2020/10/12 がスポーツの日になっていないこと（移動済み）
        assert holidays.get(_dt.date(2020, 10, 12)) is None

    def test_computed_2020_summer_olympics_moves(self) -> None:
        """2020 年の特例が「移動」していることを確認（前後の年との差分）。"""
        cal_2019 = _computed_calendar(2019)
        assert cal_2019[_dt.date(2019, 7, 15)] == "海の日"
        cal_2021 = _computed_calendar(2021)
        assert cal_2021[_dt.date(2021, 7, 19)] == "海の日"
        cal_2020 = _computed_calendar(2020)
        assert cal_2020[_dt.date(2020, 7, 23)] == "海の日"

    def test_computed_substitute_holiday(self) -> None:
        """日曜と重なった祝日の振替（例: 2029/2/11 が日曜 → 2/12 が振替）。"""
        source = _ComputedSource(from_year=2029, to_year=2029)
        holidays = {h.date: h.name for h in source.load()}
        assert holidays[_dt.date(2029, 2, 11)] == "建国記念の日"
        assert holidays[_dt.date(2029, 2, 12)] == "振替休日"

    def test_computed_substitute_holiday_with_consecutive_holiday(self) -> None:
        """振替先が祝日に重なるときは先送りされる（2026/5/3 が日曜 → 5/6 が振替）。"""
        source = _ComputedSource(from_year=2026, to_year=2026)
        holidays = {h.date: h.name for h in source.load()}
        # 5/3 (Sun) 憲法記念日 → 5/4 (Mon) みどりの日、5/5 (Tue) こどもの日 なので 5/6 が振替
        assert holidays[_dt.date(2026, 5, 6)] == "振替休日"

    def test_computed_national_holiday_silver_week(self) -> None:
        """9 月の 2 祝日に挟まれた平日がシルバーウィークとして国民の休日になる。"""
        source = _ComputedSource(from_year=2026, to_year=2026)
        holidays = {h.date: h.name for h in source.load()}
        # 2026/9/21 (Mon) 敬老の日、2026/9/22 (Tue) 国民の休日、2026/9/23 (Wed) 秋分の日
        assert holidays[_dt.date(2026, 9, 21)] == "敬老の日"
        assert holidays[_dt.date(2026, 9, 22)] == "国民の休日"
        assert holidays[_dt.date(2026, 9, 23)] == "秋分の日"

    def test_computed_vernal_equinox_2026(self) -> None:
        """2026 年の春分の日は 3/20。"""
        source = _ComputedSource(from_year=2026, to_year=2026)
        holidays = {h.date: h.name for h in source.load()}
        assert holidays[_dt.date(2026, 3, 20)] == "春分の日"

    def test_computed_emperors_birthday_changes(self) -> None:
        """天皇誕生日の日付が年で変わる（1989-2018 = 12/23、2020- = 2/23）。"""
        cal_2010 = _computed_calendar(2010)
        cal_2024 = _computed_calendar(2024)
        assert cal_2010[_dt.date(2010, 12, 23)] == "天皇誕生日"
        assert cal_2024[_dt.date(2024, 2, 23)] == "天皇誕生日"
        cal_2019 = _computed_calendar(2019)
        assert cal_2019[_dt.date(2019, 5, 1)] == "天皇の即位の日"
        assert cal_2019[_dt.date(2019, 10, 22)] == "即位礼正殿の儀の行われる日"

    def test_computed_adults_day_history(self) -> None:
        """成人の日は 1999 = 1/15、2000 = 1月 第2月曜。"""
        cal_1999 = _computed_calendar(1999)
        cal_2000 = _computed_calendar(2000)
        assert cal_1999[_dt.date(1999, 1, 15)] == "成人の日"
        assert cal_2000[_dt.date(2000, 1, 10)] == "成人の日"


class TestComputedSourceConstraints:
    """``_ComputedSource`` の運用上の制約（純粋計算・range 検証）。"""

    def test_computed_does_not_load_requests(self) -> None:
        """``_ComputedSource`` は ``requests`` を import しない（純粋計算）。"""
        import sys

        sys.modules.pop("requests", None)
        from comken.core.calendar.computed import _ComputedSource

        assert "requests" not in sys.modules, (
            "computed.py は requests を import すべきではない（純粋計算で動くソース）。"
        )

        _ComputedSource(from_year=2026, to_year=2026).load()
        assert "requests" not in sys.modules

    def test_computed_rejects_inverted_range(self) -> None:
        """``from_year > to_year`` は ``ValueError``。"""
        with pytest.raises(ValueError):
            _ComputedSource(from_year=2030, to_year=2020)

    def test_computed_warns_outside_high_precision_range(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """高精度範囲外 (1948-2099) を指定すると WARNING が残る。"""
        with caplog.at_level(logging.WARNING, logger="comken.core.calendar.computed"):
            _ComputedSource(from_year=1940, to_year=2099)
            _ComputedSource(from_year=1948, to_year=2105)
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1
        assert any("高精度" in r.getMessage() for r in warnings)

    def test_computed_default_range_is_1948_to_2099(self) -> None:
        """既定範囲は 1948-2099（タスク仕様）。"""
        source = _ComputedSource()
        holidays = source.load()
        from comken.core.calendar._calendar import Holiday

        assert Holiday(date=_dt.date(1949, 1, 1), name="元日") in holidays
        assert any(h.date.year == 2099 for h in holidays)
        assert not any(h.date.year == 2100 for h in holidays)


# ── 会社休日 ────────────────────────────────────────────────────────────


class TestCompanyHoliday:
    """``company_holiday_name`` と ``COMPANY_HOLIDAYS`` 定数の挙動。"""

    def test_year_end_and_new_year_default_present(self) -> None:
        """既定で 12/29 - 1/3 が「年末年始休暇」になる。

        12/29, 12/30, 12/31, 1/1, 1/2, 1/3 の 6 日間が会社休日に当たることを
        確認する。年跨ぎ（12→1）が正しく展開されるかも兼ねる。
        """
        assert company_holiday_name(_dt.date(2026, 12, 29)) == "年末年始休暇"
        assert company_holiday_name(_dt.date(2026, 12, 30)) == "年末年始休暇"
        assert company_holiday_name(_dt.date(2026, 12, 31)) == "年末年始休暇"
        assert company_holiday_name(_dt.date(2027, 1, 1)) == "年末年始休暇"
        assert company_holiday_name(_dt.date(2027, 1, 2)) == "年末年始休暇"
        assert company_holiday_name(_dt.date(2027, 1, 3)) == "年末年始休暇"

    def test_extra_holidays_named_company_holiday(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``COMPANY_HOLIDAYS_EXTRA`` の名称は「会社休業日」。"""
        monkeypatch.setattr(
            "comken.core.calendar.company.COMPANY_HOLIDAYS_EXTRA",
            (_dt.date(2026, 11, 4),),
        )
        assert company_holiday_name(_dt.date(2026, 11, 4)) == "会社休業日"

    def test_non_company_holiday_returns_none(self) -> None:
        """会社休日に当たらない日付は ``None``。"""
        assert company_holiday_name(_dt.date(2026, 1, 5)) is None
        assert company_holiday_name(_dt.date(2026, 7, 1)) is None

    def test_company_holiday_is_year_independent(self) -> None:
        """会社休日は年範囲に依存しない（過去・未来とも同じ月日が休み）。"""
        # 過去
        assert company_holiday_name(_dt.date(1990, 1, 2)) == "年末年始休暇"
        # 未来（内閣府 CSV の範囲外）
        assert company_holiday_name(_dt.date(2090, 12, 31)) == "年末年始休暇"
        # もっと遠く
        assert company_holiday_name(_dt.date(2200, 1, 1)) == "年末年始休暇"


# ── Approximate ─────────────────────────────────────────────────────────


class TestApproximateHoliday:
    """``Holiday.approximate`` 属性の挙動。

    計算式由来の暫定値（春分の日・秋分の日）だけ ``approximate=True`` を
    付けてして、業務フローを止めずに WARNING ログで気づけるようにする。
    """

    def test_default_approximate_is_false(self) -> None:
        """``Holiday`` の ``approximate`` は既定で False。"""
        from comken.core.calendar._calendar import Holiday

        assert Holiday(date=_dt.date(2026, 1, 1), name="元日").approximate is False

    def test_computed_marks_only_equinox_as_approximate(self) -> None:
        """Computed の春分の日・秋分の日のみ ``approximate=True``。"""
        holidays = _ComputedSource(from_year=2026, to_year=2026).load()
        for h in holidays:
            if h.name in ("春分の日", "秋分の日"):
                assert h.approximate is True, f"{h} に approximate が付いていません"
            else:
                assert h.approximate is False, f"{h} に approximate が付いています"


# ── 例外の型階層 ──────────────────────────────────────────────────────────


class TestExceptionHierarchy:
    """個別例外が ``CalendarError`` の下にまとまっているか。"""

    @pytest.mark.parametrize(
        ("exception", "expected_name"),
        [
            (CalendarSourceError("s", "r"), "CalendarSourceError"),
            (CalendarFormatError("p", "d"), "CalendarFormatError"),
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
        _set_calendar_for_test(_Calendar([]))
        try:
            # 2024-05-06 は月曜で営業日 → business_day_after は 5/7 火
            assert business_day_after(_dt.date(2024, 5, 6)) == _dt.date(2024, 5, 7)
        finally:
            _set_calendar_for_test(None)

    def test_on_or_after_includes_target(self) -> None:
        """``business_day_on_or_after`` は ``target`` が営業日ならそのまま返す。"""
        _set_calendar_for_test(_Calendar([]))
        try:
            assert business_day_on_or_after(_dt.date(2024, 5, 6)) == _dt.date(2024, 5, 6)
        finally:
            _set_calendar_for_test(None)

    def test_after_vs_on_or_after_when_target_is_business_day(self) -> None:
        """営業日を渡したとき、前者は翌日・後者はその日自身を返す。"""
        _set_calendar_for_test(_Calendar([]))
        try:
            d = _dt.date(2024, 5, 6)  # 月曜・営業日
            assert business_day_after(d) == _dt.date(2024, 5, 7)
            assert business_day_on_or_after(d) == _dt.date(2024, 5, 6)
        finally:
            _set_calendar_for_test(None)

    def test_before_excludes_target(self) -> None:
        """``business_day_before`` は ``target`` 自身を含まない（営業日でも前日）。"""
        _set_calendar_for_test(_Calendar([]))
        try:
            assert business_day_before(_dt.date(2024, 5, 6)) == _dt.date(2024, 5, 3)
        finally:
            _set_calendar_for_test(None)

    def test_on_or_before_includes_target(self) -> None:
        """``business_day_on_or_before`` は ``target`` が営業日ならそのまま返す。"""
        _set_calendar_for_test(_Calendar([]))
        try:
            assert business_day_on_or_before(_dt.date(2024, 5, 6)) == _dt.date(2024, 5, 6)
        finally:
            _set_calendar_for_test(None)

    def test_on_or_after_skips_holiday(self) -> None:
        """``target`` が祝日のとき、``on_or_after`` は翌日以降を探す。"""
        _set_calendar_for_test(_Calendar([_calendar_holiday(2024, 5, 6, "架空の祝日")]))
        try:
            assert business_day_on_or_after(_dt.date(2024, 5, 6)) == _dt.date(2024, 5, 7)
        finally:
            _set_calendar_for_test(None)


class TestNthBusinessDayOfMonth:
    """``nth_business_day_of_month`` の挙動（祝土日をまたぐ月で検証）。"""

    def test_returns_nth_business_day(self) -> None:
        """月の第 ``n`` 営業日を返す。"""
        _set_calendar_for_test(_Calendar([]))
        try:
            assert nth_business_day_of_month(_dt.date(2024, 5, 15), 3) == _dt.date(2024, 5, 3)
        finally:
            _set_calendar_for_test(None)

    def test_returns_nth_business_day_skipping_holidays(self) -> None:
        """祝土日をまたぐ月の第 ``n`` 営業日を返す。"""
        _set_calendar_for_test(
            _Calendar(
                [
                    _calendar_holiday(2024, 5, 3, "憲法"),
                    _calendar_holiday(2024, 5, 4, "みどり"),
                    _calendar_holiday(2024, 5, 5, "こどもの日"),
                    _calendar_holiday(2024, 5, 6, "振替"),
                ]
            )
        )
        try:
            assert nth_business_day_of_month(_dt.date(2024, 5, 15), 3) == _dt.date(2024, 5, 7)
        finally:
            _set_calendar_for_test(None)

    def test_returns_first_business_day(self) -> None:
        """``n == 1`` でその月の最初の営業日を返す。"""
        _set_calendar_for_test(_Calendar([]))
        try:
            assert nth_business_day_of_month(_dt.date(2024, 5, 15), 1) == _dt.date(2024, 5, 1)
        finally:
            _set_calendar_for_test(None)

    def test_raises_when_n_exceeds_month_business_days(self) -> None:
        """``n`` が月の営業日数を超えると ``BusinessDayNotFoundError``。"""
        march = [_calendar_holiday(2024, 3, d, f"holiday{d}") for d in range(1, 32)]
        _set_calendar_for_test(_Calendar(march))
        try:
            with pytest.raises(BusinessDayNotFoundError):
                nth_business_day_of_month(_dt.date(2024, 3, 15), 1)
        finally:
            _set_calendar_for_test(None)

    def test_raises_when_n_is_less_than_one(self) -> None:
        """``n < 1`` で ``BusinessDayNotFoundError``。"""
        _set_calendar_for_test(_Calendar([]))
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
        _set_calendar_for_test(_Calendar([]))
        try:
            assert last_business_day_of_month(_dt.date(2024, 8, 20)) == _dt.date(2024, 8, 30)
        finally:
            _set_calendar_for_test(None)

    def test_last_business_day_when_month_end_is_sunday(self) -> None:
        """月末が日曜のとき、金曜に戻る。"""
        _set_calendar_for_test(_Calendar([]))
        try:
            assert last_business_day_of_month(_dt.date(2024, 6, 15)) == _dt.date(2024, 6, 28)
        finally:
            _set_calendar_for_test(None)

    def test_last_business_day_when_month_end_is_holiday(self) -> None:
        """月末が祝日のとき、直前の営業日に遡る。"""
        _set_calendar_for_test(_Calendar([_calendar_holiday(2024, 4, 30, "月末祝日")]))
        try:
            assert last_business_day_of_month(_dt.date(2024, 4, 15)) == _dt.date(2024, 4, 29)
        finally:
            _set_calendar_for_test(None)

    def test_first_business_day_when_month_start_is_weekend(self) -> None:
        """月初が土日のとき、最初の営業日に進む。"""
        _set_calendar_for_test(_Calendar([]))
        try:
            assert first_business_day_of_month(_dt.date(2024, 9, 15)) == _dt.date(2024, 9, 2)
        finally:
            _set_calendar_for_test(None)

    def test_month_with_no_business_days_raises(self) -> None:
        """前後に ``BUSINESS_DAY_SEARCH_LIMIT`` を超える祝日がある月では例外。"""
        from comken.core.calendar._calendar import Holiday

        span_days = (_dt.date(2025, 12, 31) - _dt.date(2023, 1, 1)).days + 1
        assert span_days > BUSINESS_DAY_SEARCH_LIMIT * 2
        long_holidays = [
            Holiday(date=_dt.date(2023, 1, 1) + _dt.timedelta(days=i), name=f"h{i}")
            for i in range(span_days)
        ]
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
        _set_calendar_for_test(_Calendar([_calendar_holiday(2024, 1, 1, "元日")]))
        try:
            holiday_target = _dt.date(2024, 1, 1)
            assert add_business_days(holiday_target, 0) == holiday_target
        finally:
            _set_calendar_for_test(None)

    def test_positive_one_returns_business_day_after_target(self) -> None:
        """``n == 1`` で ``target`` が営業日でも**翌営業日**を返す（Excel WORKDAY 互換）。"""
        # 年末年始休暇の影響を受けない 2024/2 を使う
        _set_calendar_for_test(_Calendar([_calendar_holiday(2024, 2, 11, "建国記念")]))
        try:
            # 2024-02-13 (火) は祝日ではない営業日 + 1 営業日 → 2/14 (水)
            assert add_business_days(_dt.date(2024, 2, 13), 1) == _dt.date(2024, 2, 14)
        finally:
            _set_calendar_for_test(None)

    def test_positive_skips_weekend_and_holiday(self) -> None:
        """``n > 0`` で営業日単位に進む。"""
        _set_calendar_for_test(_Calendar([_calendar_holiday(2024, 2, 11, "建国記念")]))
        try:
            # 2024-02-13 (火) + 1 営業日 → 2/14 (水)
            assert add_business_days(_dt.date(2024, 2, 13), 1) == _dt.date(2024, 2, 14)
            # 2 営業日 → 2/15 (木)
            assert add_business_days(_dt.date(2024, 2, 13), 2) == _dt.date(2024, 2, 15)
        finally:
            _set_calendar_for_test(None)

    def test_negative_returns_previous_business_days(self) -> None:
        """``n < 0`` で ``|n|`` 営業日前に戻る。"""
        # 振替休日ロジックは company ではなく _ComputedSource 側で組み立てるため、
        # このテストでは振替休日を再現しない最小カレンダーで ``add_business_days``
        # の動作だけを見る。
        _set_calendar_for_test(_Calendar([_calendar_holiday(2024, 2, 11, "建国記念")]))
        try:
            # 2024-02-14 (水) -1 → 2/13 (火)
            assert add_business_days(_dt.date(2024, 2, 14), -1) == _dt.date(2024, 2, 13)
            # -2 → 2/12 (月) (振替休日はカレンダーに無いのでそのまま戻る)
            assert add_business_days(_dt.date(2024, 2, 14), -2) == _dt.date(2024, 2, 12)
        finally:
            _set_calendar_for_test(None)


class TestBusinessDaySearchLimit:
    """探索上限に達すると ``BusinessDayNotFoundError`` になることを確認。"""

    def test_raises_after_search_limit_when_all_days_are_holidays(self) -> None:
        """全日が祝日のカレンダーで ``business_day_after`` が上限到達で例外。"""
        from comken.core.calendar._calendar import Holiday

        holidays = [
            Holiday(
                date=_dt.date(2025, 1, 1) + _dt.timedelta(days=i), name="h"
            )
            for i in range(BUSINESS_DAY_SEARCH_LIMIT + 100)
        ]
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
        _set_calendar_for_test(_bundled_calendar())
        try:
            assert business_day_after(_dt.date(2026, 5, 3)) == _dt.date(2026, 5, 7)
        finally:
            _set_calendar_for_test(None)

    def test_business_day_on_or_after_from_may_3(self) -> None:
        """``business_day_on_or_after(2026/5/3)`` は GW 後の 5/7 を返す。"""
        _set_calendar_for_test(_bundled_calendar())
        try:
            assert business_day_on_or_after(_dt.date(2026, 5, 3)) == _dt.date(2026, 5, 7)
        finally:
            _set_calendar_for_test(None)

    def test_business_day_after_from_weekday_uses_next(self) -> None:
        """``business_day_after(2026/5/1 金曜)`` は 5/7 木曜。"""
        _set_calendar_for_test(_bundled_calendar())
        try:
            assert business_day_after(_dt.date(2026, 5, 1)) == _dt.date(2026, 5, 7)
        finally:
            _set_calendar_for_test(None)

    def test_business_day_on_or_after_from_weekday_returns_target(self) -> None:
        """``business_day_on_or_after(2026/5/1 金曜)`` は 5/1 そのものを返す。"""
        _set_calendar_for_test(_bundled_calendar())
        try:
            assert business_day_on_or_after(_dt.date(2026, 5, 1)) == _dt.date(2026, 5, 1)
        finally:
            _set_calendar_for_test(None)

    def test_business_day_on_or_before_15th(self) -> None:
        """「15日、休みならその前の営業日」の例（``business_day_on_or_before``）。"""
        _set_calendar_for_test(_bundled_calendar())
        try:
            assert business_day_on_or_before(_dt.date(2026, 5, 15)) == _dt.date(2026, 5, 15)
            assert business_day_on_or_before(_dt.date(2026, 5, 16)) == _dt.date(2026, 5, 15)
        finally:
            _set_calendar_for_test(None)


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


# ── export_csv ────────────────────────────────────────────────────────────


class TestExportCsv:
    """``export_csv`` の挙動。"""

    def test_writes_header_and_rows_sorted_by_date(self, tmp_path: Path) -> None:
        """ヘッダーと日付順の行を書き出す。"""
        out = tmp_path / "holidays.csv"
        result = export_csv(out)

        assert result == out
        text = out.read_text(encoding="utf-8-sig")
        lines = text.splitlines()
        assert lines[0] == "date,name,approximate"
        assert lines[1] == "1948-01-01,年末年始休暇,False"
        dates_in_file = [line.split(",")[0] for line in lines[1:]]
        assert dates_in_file == sorted(dates_in_file)

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """親ディレクトリが無ければ作る。"""
        out = tmp_path / "nested" / "dir" / "holidays.csv"
        export_csv(out)
        assert out.exists()

    def test_default_encoding_is_utf8_with_bom(self, tmp_path: Path) -> None:
        """既定は utf-8-sig（BOM付き）。Excelで文字化けしないため。"""
        out = tmp_path / "holidays.csv"
        export_csv(out)
        raw = out.read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf")

    def test_default_path_is_exported_csv_path(self) -> None:
        """path省略時は ``EXPORTED_CSV_PATH``（内閣府CSVと同じ data/ フォルダ）に書く。"""
        assert BUNDLED_CSV_PATH.parent / "holidays.csv" == EXPORTED_CSV_PATH
        assert EXPORTED_CSV_PATH.exists()

    def test_export_result_is_independent_of_today(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """``export_csv`` の結果が呼ぶ日に依存しない。

        ``comken.core.clock.today`` を別日付に差し替えても、出力内容が
        同じになることを確認する（国民の祝日は内閣府 CSV 由来、
        会社休日はルール判定のため固定）。
        """
        from comken.core import clock as clock_module

        out_a = tmp_path / "today_a.csv"
        out_b = tmp_path / "today_b.csv"

        monkeypatch.setattr(clock_module, "today", lambda: _dt.date(2020, 1, 1))
        export_csv(out_a)
        monkeypatch.setattr(clock_module, "today", lambda: _dt.date(2099, 1, 1))
        export_csv(out_b)

        text_a = out_a.read_text(encoding="utf-8-sig")
        text_b = out_b.read_text(encoding="utf-8-sig")
        assert text_a == text_b

    def test_export_includes_company_holidays(self, tmp_path: Path) -> None:
        """国民の祝日＋会社休日が同じ CSV にまとめて書き出される。

        国民の祝日と同じ日に会社休日がある場合は国民の祝日が先勝ちで
        1行になる。
        """
        out = tmp_path / "holidays.csv"
        export_csv(out)
        with out.open(encoding="utf-8-sig", newline="") as file:
            rows = list(csv.reader(file))
        header, data = rows[0], rows[1:]
        assert header == ["date", "name", "approximate"]
        # 2026/1/1 は元日（国民の祝日）+ 年末年始休暇（会社休日）→ 国民の祝日が先勝ち
        names_for_jan1 = [row[1] for row in data if row[0] == "2026-01-01"]
        assert names_for_jan1 == ["元日"]
        # 2026/12/30 は年末年始休暇
        assert any(row[0] == "2026-12-30" and row[1] == "年末年始休暇" for row in data)
        # 2026/5/3 は国民の祝日（憲法記念日）→ そのまま出る
        assert any(row[0] == "2026-05-03" and row[1] == "憲法記念日" for row in data)


class TestCsvSynchronization:
    """``data/holidays.csv`` の追跡物との同期テスト。

    ``export_csv()`` の結果が ``data/holidays.csv``（git 管理下）と
    行ごとに一致していることを確認する。CSV のフォーマット変更・
    内閣府 CSV 更新・会社休日ルール変更後に ``python tools\\export_calendar.py``
    を再実行するのを忘れた場合に落ちる。
    """

    def test_exported_matches_bundled_holidays_csv(self) -> None:
        """``export_csv()`` の出力が ``data/holidays.csv`` と一致する。"""
        bundled = BUNDLED_CSV_PATH.parent / "holidays.csv"
        assert bundled.exists(), (
            "data/holidays.csv がまだ生成されていません。"
            " `python tools\\export_calendar.py` を実行してください。"
        )

        with bundled.open(encoding="utf-8-sig", newline="") as file:
            bundled_rows = list(csv.reader(file))
        bundled_header, bundled_data = bundled_rows[0], bundled_rows[1:]

        # 一時ディレクトリに出して比較（依存しないように毎回生成）
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.csv"
            export_csv(out)
            with out.open(encoding="utf-8-sig", newline="") as file:
                exported_rows = list(csv.reader(file))
        exported_header, exported_data = exported_rows[0], exported_rows[1:]

        assert exported_header == bundled_header, (
            "data/holidays.csv のヘッダーが export_csv() と一致しません。"
            " `python tools/export_calendar.py` を実行して holidays.csv を"
            " 更新しコミットしてください。"
        )
        assert exported_data == bundled_data, (
            "data/holidays.csv の内容が export_csv() と一致しません。"
            " `python tools/export_calendar.py` を実行して holidays.csv を"
            " 更新しコミットしてください。"
        )


# ── モジュール・定数 ──────────────────────────────────────────────────────


class TestModuleConstants:
    """公開定数の形と値のチェック。"""

    def test_business_day_search_limit_is_30(self) -> None:
        """``BUSINESS_DAY_SEARCH_LIMIT`` は 30（休日広範囲時の無限ループ防止）。"""
        assert BUSINESS_DAY_SEARCH_LIMIT == 30

    def test_expiring_warning_days_is_30(self) -> None:
        """``EXPIRING_WARNING_DAYS`` は 30（期限切れ検知の閾値）。"""
        assert EXPIRING_WARNING_DAYS == 30

    def test_bundled_csv_path_points_to_data_folder(self) -> None:
        """``BUNDLED_CSV_PATH`` は data/syukujitsu.csv。"""
        assert BUNDLED_CSV_PATH.name == "syukujitsu.csv"
        assert BUNDLED_CSV_PATH.parent.name == "data"

    def test_exported_csv_path_points_to_data_folder(self) -> None:
        """``EXPORTED_CSV_PATH`` は data/holidays.csv。"""
        assert EXPORTED_CSV_PATH.name == "holidays.csv"
        assert EXPORTED_CSV_PATH.parent.name == "data"
