"""comken.core.holidays（および re-export する comken.toolbox.holidays）のテスト。

内閣府の祝日 CSV（CP932 エンコード）と会社の休業日ソース、
ソース Protocol の各経路を横断的に検証する。
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import logging
from pathlib import Path

import pytest

from comken.core.holidays import (
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
from comken.core.holidays.sources.company import CompanyHolidaySource
from comken.core.holidays.sources.computed import ComputedHolidaySource
from comken.exceptions import (
    BusinessDayNotFoundError,
    HolidayCalendarError,
    HolidayCalendarFetchError,
    HolidayCalendarFormatError,
    HolidayCalendarSourceError,
)
from comken.toolbox.holidays import CabinetOfficeCSVSource

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "holidays" / "syukujitsu_sample.csv"


# ── Holiday データクラス ──────────────────────────────────────────────────


def _computed_calendar(year: int) -> dict[_dt.date, str]:
    """その年の ``{日付: 祝日名}`` を計算で作る。

    ``ComputedHolidaySource(from_year=..., to_year=...)`` を毎回書くと 1 行が
    100 桁を超えて折り返しが増え、「何年を見ているのか」が読み取りにくくなる。
    """
    return {h.date: h.name for h in ComputedHolidaySource(from_year=year, to_year=year).load()}


class TestHolidayDataclass:
    """``Holiday`` の不変性・ハッシュ可能性を確認する。"""

    def test_fields_are_accessible(self) -> None:
        """``date`` と ``name`` が属性で読める。"""
        holiday = Holiday(date=_dt.date(2024, 1, 1), name="元日")
        assert holiday.date == _dt.date(2024, 1, 1)
        assert holiday.name == "元日"

    def test_is_frozen(self) -> None:
        """``frozen=True`` でフィールドを書き換えられない。"""
        holiday = Holiday(date=_dt.date(2024, 1, 1), name="元日")
        with pytest.raises(dataclasses.FrozenInstanceError):
            holiday.date = _dt.date(2024, 1, 2)  # type: ignore[misc]

    def test_is_hashable_and_equals_by_value(self) -> None:
        """同じ値なら ``set`` に入れたり ``==`` で一致する。"""
        a = Holiday(date=_dt.date(2024, 1, 1), name="元日")
        b = Holiday(date=_dt.date(2024, 1, 1), name="元日")
        assert a == b
        assert {a, b} == {a}

    def test_inequality_when_name_differs(self) -> None:
        """名称が違うと別物扱いされる。"""
        a = Holiday(date=_dt.date(2024, 1, 1), name="元日")
        b = Holiday(date=_dt.date(2024, 1, 1), name="年始休暇")
        assert a != b


# ── 内閣府 CSV ローダー ──────────────────────────────────────────────────


class TestCabinetOfficeCsvLoader:
    """内閣府 CSV（CP932）の読み取り。"""

    def test_loads_real_format(self) -> None:
        """fixture を CP932 で読んで Holiday に変換できる。"""
        from comken.core.holidays.csv_source import load_cabinet_office_csv

        holidays = load_cabinet_office_csv(FIXTURE_PATH)

        assert holidays, "1件以上読み取れるべき"
        # fixture 内では「元日」が 2024 / 2025 / 2026 で揃う
        dates = {h.date for h in holidays}
        assert _dt.date(2024, 1, 1) in dates
        assert _dt.date(2025, 1, 1) in dates
        assert _dt.date(2026, 1, 1) in dates
        # 名称はそのまま入る
        assert Holiday(date=_dt.date(2024, 5, 3), name="憲法記念日") in holidays
        # ヘッダー行は結果に含まれない
        assert all(h.name != "国民の祝日・休日名称" for h in holidays)

    def test_missing_file_raises_format_error(self, tmp_path: Path) -> None:
        """ファイルが無ければ ``HolidayCalendarFormatError``。"""
        from comken.core.holidays.csv_source import load_cabinet_office_csv

        missing = tmp_path / "nope.csv"
        with pytest.raises(HolidayCalendarFormatError):
            load_cabinet_office_csv(missing)

    def test_garbage_text_raises_format_error(self, tmp_path: Path) -> None:
        """日付として読めない文字列だけだと ``HolidayCalendarFormatError``。"""
        from comken.core.holidays.csv_source import load_cabinet_office_csv

        bad = tmp_path / "bad.csv"
        bad.write_text("hello,world\nfoo,bar\n", encoding="cp932")
        with pytest.raises(HolidayCalendarFormatError):
            load_cabinet_office_csv(bad)

    def test_wrong_encoding_raises_format_error(self, tmp_path: Path) -> None:
        """CP932 以外の文字コードで書かれたものは読めない（FormatError）。"""
        from comken.core.holidays.csv_source import load_cabinet_office_csv

        utf8 = tmp_path / "utf8.csv"
        # fixture をそのまま UTF-8 で書いたものを作る（CP932 と食い違う）
        utf8.write_text(
            "国民の祝日・休日月日,国民の祝日・休日名称\n2024-01-01,元日\n",
            encoding="utf-8",
        )
        with pytest.raises(HolidayCalendarFormatError):
            load_cabinet_office_csv(utf8)


# ── HolidayCalendar の判定 ──────────────────────────────────────────────


def _fixture_calendar() -> HolidayCalendar:
    """テスト用の小さな ``HolidayCalendar`` を fixture から組み立てる。"""
    return HolidayCalendar.from_csv(FIXTURE_PATH)


class TestHolidayCalendarBasic:
    """``is_holiday`` / ``holidays_in`` / ``holiday_names`` の基本判定。"""

    def test_is_holiday_true_for_new_years_day(self) -> None:
        """元日は祝日扱い。"""
        cal = _fixture_calendar()
        assert cal.is_holiday(_dt.date(2024, 1, 1)) is True

    def test_is_holiday_false_for_normal_weekday(self) -> None:
        """祝日でなければ ``False``。"""
        cal = _fixture_calendar()
        # 2024-01-02 は火曜で祝日でない
        assert cal.is_holiday(_dt.date(2024, 1, 2)) is False

    def test_is_holiday_handles_dates_outside_known_range(self) -> None:
        """収録範囲外（収録最終日以降）は祝日扱いしない。"""
        cal = _fixture_calendar()
        last = cal.last_known_date()
        assert last is not None
        next_day = last + _dt.timedelta(days=1)
        assert cal.is_holiday(next_day) is False

    def test_holidays_in_returns_sorted_subset(self) -> None:
        """``holidays_in`` が期間内の祝日を日付昇順で返す。"""
        cal = _fixture_calendar()
        result = cal.holidays_in(_dt.date(2024, 5, 1), _dt.date(2024, 5, 7))
        assert [h.date for h in result] == [
            _dt.date(2024, 5, 3),
            _dt.date(2024, 5, 4),
            _dt.date(2024, 5, 5),
        ]

    def test_holidays_in_empty_when_start_after_end(self) -> None:
        """``start > end`` のときは空リスト。"""
        cal = _fixture_calendar()
        assert cal.holidays_in(_dt.date(2025, 1, 1), _dt.date(2024, 12, 31)) == []

    def test_holiday_names_returns_tuple(self) -> None:
        """``holiday_names`` は ``Sequence[str]`` を返す。"""
        cal = _fixture_calendar()
        names = cal.holiday_names(_dt.date(2024, 1, 1))
        assert tuple(names) == ("元日",)

    def test_holiday_names_empty_for_non_holiday(self) -> None:
        """祝日でなければ空タプル。"""
        cal = _fixture_calendar()
        assert tuple(cal.holiday_names(_dt.date(2024, 1, 2))) == ()


class TestIsBusinessDay:
    """``is_business_day`` の挙動（週末スキップ・週末スキップなし）。"""

    def test_weekday_non_holiday_is_business_day(self) -> None:
        """祝日でない月曜は営業日。"""
        cal = _fixture_calendar()
        assert is_business_day(_dt.date(2024, 1, 2), calendar=cal) is True  # 火曜

    def test_weekday_holiday_is_not_business_day(self) -> None:
        """祝日の月曜は営業日ではない。"""
        cal = _fixture_calendar()
        assert is_business_day(_dt.date(2024, 1, 1), calendar=cal) is False

    def test_saturday_is_skipped_by_default(self) -> None:
        """土曜は ``skip_weekends=True``（既定）で休業。"""
        cal = _fixture_calendar()
        assert is_business_day(_dt.date(2024, 1, 6), calendar=cal) is False  # 土曜

    def test_sunday_is_skipped_by_default(self) -> None:
        """日曜は ``skip_weekends=True``（既定）で休業。"""
        cal = _fixture_calendar()
        assert is_business_day(_dt.date(2024, 1, 7), calendar=cal) is False  # 日曜

    def test_saturday_is_business_when_skip_weekends_false(self) -> None:
        """``skip_weekends=False`` なら土曜でも祝日でなければ営業日。"""
        cal = _fixture_calendar()
        assert is_business_day(_dt.date(2024, 1, 6), calendar=cal, skip_weekends=False) is True

    def test_holiday_saturday_still_not_business(self) -> None:
        """土曜でも祝日なら ``False``（``skip_weekends=False`` でも）。"""
        cal = _fixture_calendar()
        # 2024-05-04 は土曜かつ祝日（みどりの日）
        assert is_business_day(_dt.date(2024, 5, 4), calendar=cal, skip_weekends=False) is False


class TestBusinessDayAfter:
    """``business_day_after`` の挙動。"""

    def test_skips_weekend_and_holiday(self) -> None:
        """週末と祝日の両方を飛ばす。"""
        cal = _fixture_calendar()
        # 2024-05-02 は木曜 → 翌営業は 2024-05-06（月）= 5/3,4,5 を飛ばす
        assert business_day_after(_dt.date(2024, 5, 2), calendar=cal) == _dt.date(2024, 5, 6)

    def test_skips_only_holiday_when_target_is_weekday(self) -> None:
        """``target`` が平日のとき、祝日だけ飛ばす。"""
        cal = _fixture_calendar()
        # 2024-04-30 は火曜 → 4/29 が昭和の日（祝）で、5/1 は祝日ではないので 5/1 が翌営業
        assert business_day_after(_dt.date(2024, 4, 30), calendar=cal) == _dt.date(2024, 5, 1)

    def test_business_day_after_respects_skip_weekends_flag(self) -> None:
        """``skip_weekends=False`` でも翌日が祝日なら飛ばす。"""
        cal = _fixture_calendar()
        # 2024-01-01 は祝日かつ月曜 → 翌営業は 2024-01-02 の火曜
        assert business_day_after(
            _dt.date(2024, 1, 1), calendar=cal, skip_weekends=False
        ) == _dt.date(2024, 1, 2)

    def test_target_is_business_day_returns_next_one(self) -> None:
        """``target`` が営業日でも翌営業日を返す（自身を含まない）。"""
        cal = _fixture_calendar()
        # 2024-05-02 (木) は営業日 → 翌営業は 2024-05-06 (月)
        assert business_day_after(_dt.date(2024, 5, 2), calendar=cal) == _dt.date(2024, 5, 6)


class TestExpiry:
    """``expires_after`` / ``days_until_expiry`` / ``last_known_date`` の挙動。"""

    def test_last_known_date_is_max(self) -> None:
        """``last_known_date`` は収録済み祝日のうち最新の日付。"""
        cal = _fixture_calendar()
        last = cal.last_known_date()
        # fixture の最終日は 2026-11-03（文化の日）
        assert last == _dt.date(2026, 11, 3)

    def test_expires_after_true_when_past_last_known(self) -> None:
        """最終日より後の日付は期限切れ。"""
        cal = _fixture_calendar()
        last = cal.last_known_date()
        assert last is not None
        assert cal.expires_after(last + _dt.timedelta(days=1)) is True
        # 最終日当日は「収録済み」扱い（境界は is_business_day 側で注意）
        assert cal.expires_after(last) is True

    def test_expires_after_false_when_before_last_known(self) -> None:
        """最終日より前は期限切れではない。"""
        cal = _fixture_calendar()
        last = cal.last_known_date()
        assert last is not None
        assert cal.expires_after(_dt.date(2024, 1, 1)) is False

    def test_days_until_expiry_positive(self) -> None:
        """未来の日付を引くと正の日数。"""
        cal = _fixture_calendar()
        last = cal.last_known_date()
        assert last is not None
        assert cal.days_until_expiry(_dt.date(2024, 1, 1)) == (last - _dt.date(2024, 1, 1)).days

    def test_empty_calendar_is_expired(self) -> None:
        """祝日が 1件も無いときは「最初から期限切れ」扱い。"""
        empty = HolidayCalendar([])
        assert empty.last_known_date() is None
        assert empty.expires_after(_dt.date(2024, 1, 1)) is True
        assert empty.days_until_expiry(_dt.date(2024, 1, 1)) == -1


class TestExpiringWarning:
    """期限切れ警告（30日切ったら 1度だけ WARNING）の挙動。"""

    def test_warning_logged_once_when_within_30_days(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """残り 30 日未満のとき WARNING が出る（同じ日で 1度だけ）。"""
        cal = HolidayCalendar([Holiday(date=_dt.date(2024, 5, 5), name="こどもの日")])
        today = _dt.date(2024, 4, 20)  # 残り 15 日
        with caplog.at_level(logging.WARNING, logger="comken.core.holidays.calendar"):
            is_business_day(today, calendar=cal)
            is_business_day(today, calendar=cal)  # 2回呼んでも 1度だけ
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "15" in warnings[0].getMessage()

    def test_warning_not_logged_when_far_from_expiry(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """30日以上先なら警告は出ない。"""
        cal = HolidayCalendar([Holiday(date=_dt.date(2025, 5, 5), name="こどもの日")])
        today = _dt.date(2024, 1, 1)
        with caplog.at_level(logging.WARNING, logger="comken.core.holidays.calendar"):
            is_business_day(today, calendar=cal)
        assert not [r for r in caplog.records if r.levelno == logging.WARNING]

    def test_warning_not_repeated_on_next_day(self, caplog: pytest.LogCaptureFixture) -> None:
        """翌日にもう一度 ``is_business_day`` を呼ぶと、その日では 1度だけ出る。"""
        cal = HolidayCalendar([Holiday(date=_dt.date(2024, 5, 5), name="こどもの日")])
        with caplog.at_level(logging.WARNING, logger="comken.core.holidays.calendar"):
            is_business_day(_dt.date(2024, 4, 20), calendar=cal)
            is_business_day(_dt.date(2024, 4, 21), calendar=cal)
            is_business_day(_dt.date(2024, 4, 21), calendar=cal)
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 2


# ── from_sources / マージ ──────────────────────────────────────────────


class TestFromSources:
    """``HolidayCalendar.from_sources`` のマージ動作。"""

    def test_merges_multiple_sources(self) -> None:
        """複数の ``HolidaySource`` を 1つのカレンダーにまとめられる。"""
        from comken.core.holidays.csv_source import parse_cabinet_office_text

        sample_a = "国民の祝日・休日月日,国民の祝日・休日名称\n2024-01-01,元日\n"
        sample_b = "国民の祝日・休日月日,国民の祝日・休日名称\n2024-11-04,創立記念日\n"

        class _InlineSource:
            def __init__(self, text: str) -> None:
                self._text = text

            def load(self) -> list[Holiday]:
                return parse_cabinet_office_text(self._text, source="inline")

        cal = HolidayCalendar.from_sources([_InlineSource(sample_a), _InlineSource(sample_b)])
        dates = {h.date for h in cal.all_holidays()}
        assert _dt.date(2024, 1, 1) in dates
        assert _dt.date(2024, 11, 4) in dates

    def test_first_source_wins_on_duplicate_date(self, caplog: pytest.LogCaptureFixture) -> None:
        """同じ日付が複数のソースにあるとき、先勝ちで採用される（警告は出ない）。

        内閣府 CSV と会社の年末年始休暇など、複数 source が同じ日を返すのは
        正常な状態。``HolidayCalendar`` 側では警告を出さず黙って先を採用する。
        """
        from comken.core.holidays.csv_source import parse_cabinet_office_text

        sample_a = "国民の祝日・休日月日,国民の祝日・休日名称\n2024-01-01,元日（内閣府）\n"
        sample_b = "国民の祝日・休日月日,国民の祝日・休日名称\n2024-01-01,元日（管理表）\n"

        class _InlineSource:
            def __init__(self, text: str) -> None:
                self._text = text

            def load(self) -> list[Holiday]:
                return parse_cabinet_office_text(self._text, source="inline")

        with caplog.at_level(logging.WARNING, logger="comken.core.holidays.calendar"):
            cal = HolidayCalendar.from_sources([_InlineSource(sample_a), _InlineSource(sample_b)])
        names = tuple(cal.holiday_names(_dt.date(2024, 1, 1)))
        # 先勝ちなので「内閣府」の名称が残る
        assert names == ("元日（内閣府）",)
        # 重複でも警告は出ない
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert not any("重複" in r.getMessage() for r in warnings)


# ── Protocol 動作 ─────────────────────────────────────────────────────────


class TestProtocol:
    """``HolidaySource`` が Protocol として機能するか。"""

    def test_object_satisfying_protocol_is_instance(self) -> None:
        """``load`` を持つ素のクラスでも Protocol を満たせば isinstance で True。"""

        class _CustomSource:
            def load(self) -> list[Holiday]:
                return [Holiday(date=_dt.date(2024, 1, 1), name="元日")]

        source = _CustomSource()
        assert isinstance(source, HolidaySource)


# ── モジュールレベル関数 ──────────────────────────────────────────────────


class TestModuleLevelFunction:
    """``is_business_day`` モジュール関数の挙動。"""

    def test_delegates_to_calendar(self) -> None:
        """``HolidayCalendar._is_business_day`` に委譲する。"""
        cal = _fixture_calendar()
        assert is_business_day(_dt.date(2024, 1, 2), calendar=cal) == cal._is_business_day(
            _dt.date(2024, 1, 2)
        )
        # 祝日側は ``False``
        assert is_business_day(_dt.date(2024, 1, 1), calendar=cal) is False

    def test_calendar_is_keyword_only(self) -> None:
        """``calendar`` はキーワード専用。位置引数だとエラー。"""
        cal = _fixture_calendar()
        with pytest.raises(TypeError):
            is_business_day(_dt.date(2024, 1, 2), cal)  # type: ignore[misc]


# ── CabinetOfficeCSVSource ────────────────────────────────────────────────


class _StubResponse:
    """requests のレスポンスを模倣する最小スタブ。"""

    def __init__(self, content: bytes, status_code: int = 200) -> None:
        self.content = content
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")


class TestCabinetOfficeCsvSource:
    """``CabinetOfficeCSVSource`` のキャッシュ・フェッチ失敗フォールバック。"""

    def test_uses_cache_when_present(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """キャッシュ済みならそのまま使う（ダウンロードを呼ばない）。"""
        cache = tmp_path / "cache.csv"
        cache.write_bytes(
            "国民の祝日・休日月日,国民の祝日・休日名称\n2024-01-01,元日\n".encode("cp932")
        )

        called = {"count": 0}

        def _fake_get(*args, **kwargs):
            called["count"] += 1
            return _StubResponse(b"unused")

        monkeypatch.setattr("requests.get", _fake_get)
        # requests が無い環境でも動かすため、sys.modules にダミーを入れる
        import sys
        import types

        if "requests" not in sys.modules:
            requests_module = types.ModuleType("requests")
            requests_module.get = _fake_get  # type: ignore[attr-defined]
            sys.modules["requests"] = requests_module

        source = CabinetOfficeCSVSource(cache_path=cache)
        holidays = list(source.load())
        assert called["count"] == 0, "キャッシュがあればリクエストを呼ばない"
        assert holidays[0].name == "元日"

    def test_downloads_when_cache_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """キャッシュが無ければダウンロードしてキャッシュを更新する。"""
        cache = tmp_path / "cache.csv"
        body = "国民の祝日・休日月日,国民の祝日・休日名称\n2024-02-11,建国記念の日\n".encode(
            "cp932"
        )
        called = {"count": 0}

        def _fake_get(*args, **kwargs):
            called["count"] += 1
            return _StubResponse(body)

        import sys
        import types

        if "requests" not in sys.modules:
            requests_module = types.ModuleType("requests")
            requests_module.get = _fake_get  # type: ignore[attr-defined]
            sys.modules["requests"] = requests_module
        monkeypatch.setattr("requests.get", _fake_get)

        source = CabinetOfficeCSVSource(cache_path=cache)
        holidays = list(source.load())
        assert called["count"] == 1, "キャッシュが無ければリクエストを呼ぶ"
        assert holidays[0].name == "建国記念の日"
        # キャッシュも更新されている
        assert cache.read_bytes() == body

    def test_raises_fetch_error_when_no_cache_and_network_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """キャッシュも無い + 取得失敗 → ``HolidayCalendarFetchError``。"""
        import sys
        import types

        def _failing_get(*args, **kwargs):
            import requests  # type: ignore[import-not-found]

            raise requests.RequestException("no network")  # type: ignore[attr-defined]

        requests_module = types.ModuleType("requests")
        requests_module.get = _failing_get  # type: ignore[attr-defined]
        requests_module.RequestException = type(  # type: ignore[attr-defined]
            "RequestException", (Exception,), {}
        )
        sys.modules["requests"] = requests_module
        monkeypatch.setattr("requests.get", _failing_get)

        cache = tmp_path / "no_cache.csv"
        source = CabinetOfficeCSVSource(cache_path=cache)
        with pytest.raises(HolidayCalendarFetchError):
            list(source.load())


# ── 例外の型階層 ─────────────────────────────────────────────────────────


class TestExceptionHierarchy:
    """個別例外が ``HolidayCalendarError`` の下にまとまっているか。"""

    @pytest.mark.parametrize(
        ("exception", "expected_name"),
        [
            (HolidayCalendarFetchError("u", "r"), "HolidayCalendarFetchError"),
            (HolidayCalendarSourceError("s", "r"), "HolidayCalendarSourceError"),
            (HolidayCalendarFormatError("p", "d"), "HolidayCalendarFormatError"),
        ],
    )
    def test_isinstance_of_base(self, exception: HolidayCalendarError, expected_name: str) -> None:
        """全ての個別例外が ``HolidayCalendarError`` および ``ComkenError`` の派生。"""
        assert isinstance(exception, HolidayCalendarError)
        assert isinstance(exception, Exception)
        assert type(exception).__name__ == expected_name


# ── 遅延 import 確認 ──────────────────────────────────────────────────────


class TestNoImplicitRequests:
    """モジュール import 時に ``requests`` が読まれないことを確認する。"""

    def test_importing_holidays_does_not_load_requests(self) -> None:
        """``comken.toolbox.holidays`` を import しても ``requests`` は入らない。

        オフライン環境（社内 BO 端末）で requests が無い PC でも
        ``HolidayCalendar.is_business_day`` などが動くことを保証する。
        """
        import sys

        # 他のテストが ``sys.modules["requests"]`` にダミーを入れているので、
        # このテストではまっさらな状態から import し直す
        for name in (
            "requests",
            "comken.toolbox.holidays",
            "comken.core.holidays",
            "comken.core.holidays.calendar",
            "comken.core.holidays.csv_source",
            "comken.core.holidays.sources",
            "comken.core.holidays.sources.computed",
            "comken.core.holidays.sources.company",
            "comken.toolbox.holidays.exceptions",
            "comken.toolbox.holidays.sources",
            "comken.toolbox.holidays.sources.cabinet_office",
        ):
            sys.modules.pop(name, None)

        import comken.toolbox.holidays  # noqa: F401

        assert "requests" not in sys.modules, (
            "requests が import 時に読込まれています。"
            "CabinetOfficeCSVSource._download 内で遅延 import してください。"
        )


# ── ComputedHolidaySource ───────────────────────────────────────────────


class TestComputedHolidaySource:
    """``ComputedHolidaySource`` の出力（mokejp/holidays_jp のアルゴリズム）。"""

    def test_computed_returns_all_2026_holidays(self) -> None:
        """2026 年の国民の祝日全部を個別に assert する。

        会社休日（年末年始休暇など）は ``CompanyHolidaySource`` 側で表現する
        ようになったので、ここでは国民の祝日だけを確認する。
        """
        source = ComputedHolidaySource(from_year=2026, to_year=2026)
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
        source = ComputedHolidaySource(from_year=2020, to_year=2020)
        holidays = {h.date: h.name for h in source.load()}
        assert holidays[_dt.date(2020, 7, 23)] == "海の日"
        assert holidays[_dt.date(2020, 7, 24)] == "スポーツの日"
        assert holidays[_dt.date(2020, 8, 10)] == "山の日"
        # 2020/10/12 がスポーツの日になっていないこと（移動済み）
        assert holidays.get(_dt.date(2020, 10, 12)) is None

    def test_computed_2020_summer_olympics_moves(self) -> None:
        """2020 年の特例が「移動」していることを確認（前後の年との差分）。"""
        # 2019 年は 7月 第3月曜 = 7/15 が海の日
        cal_2019 = _computed_calendar(2019)
        assert cal_2019[_dt.date(2019, 7, 15)] == "海の日"
        # 2021 年は 7月 第3月曜 = 7/19 が海の日（オリンピック特例の解除）
        cal_2021 = _computed_calendar(2021)
        assert cal_2021[_dt.date(2021, 7, 19)] == "海の日"
        # 2020 年だけ 7/23
        cal_2020 = _computed_calendar(2020)
        assert cal_2020[_dt.date(2020, 7, 23)] == "海の日"

    def test_computed_substitute_holiday(self) -> None:
        """日曜と重なった祝日の振替（例: 2029/2/11 が日曜 → 2/12 が振替）。"""
        source = ComputedHolidaySource(from_year=2029, to_year=2029)
        holidays = {h.date: h.name for h in source.load()}
        assert holidays[_dt.date(2029, 2, 11)] == "建国記念の日"
        assert holidays[_dt.date(2029, 2, 12)] == "振替休日"

    def test_computed_substitute_holiday_with_consecutive_holiday(self) -> None:
        """振替先が祝日に重なるときは先送りされる（2026/5/3 が日曜 → 5/6 が振替）。"""
        source = ComputedHolidaySource(from_year=2026, to_year=2026)
        holidays = {h.date: h.name for h in source.load()}
        # 5/3 (Sun) 憲法記念日 → 5/4 (Mon) みどりの日、5/5 (Tue) こどもの日 なので 5/6 が振替
        assert holidays[_dt.date(2026, 5, 6)] == "振替休日"

    def test_computed_national_holiday_silver_week(self) -> None:
        """9 月の 2 祝日に挟まれた平日がシルバーウィークとして国民の休日になる。"""
        source = ComputedHolidaySource(from_year=2026, to_year=2026)
        holidays = {h.date: h.name for h in source.load()}
        # 2026/9/21 (Mon) 敬老の日、2026/9/22 (Tue) 国民の休日、2026/9/23 (Wed) 秋分の日
        assert holidays[_dt.date(2026, 9, 21)] == "敬老の日"
        assert holidays[_dt.date(2026, 9, 22)] == "国民の休日"
        assert holidays[_dt.date(2026, 9, 23)] == "秋分の日"

    def test_computed_vernal_equinox_2026(self) -> None:
        """2026 年の春分の日は 3/20。"""
        source = ComputedHolidaySource(from_year=2026, to_year=2026)
        holidays = {h.date: h.name for h in source.load()}
        assert holidays[_dt.date(2026, 3, 20)] == "春分の日"

    def test_computed_emperors_birthday_changes(self) -> None:
        """天皇誕生日の日付が年で変わる（1989-2018 = 12/23、2020- = 2/23）。"""
        cal_2010 = _computed_calendar(2010)
        cal_2024 = _computed_calendar(2024)
        # 平成: 12/23
        assert cal_2010[_dt.date(2010, 12, 23)] == "天皇誕生日"
        # 令和: 2/23
        assert cal_2024[_dt.date(2024, 2, 23)] == "天皇誕生日"
        # 2019 は変則（天皇の即位の日 = 5/1、即位礼正殿の儀 = 10/22）
        cal_2019 = _computed_calendar(2019)
        assert cal_2019[_dt.date(2019, 5, 1)] == "天皇の即位の日"
        assert cal_2019[_dt.date(2019, 10, 22)] == "即位礼正殿の儀の行われる日"

    def test_computed_adults_day_history(self) -> None:
        """成人の日は 1999 = 1/15、2000 = 1月 第2月曜。"""
        cal_1999 = _computed_calendar(1999)
        cal_2000 = _computed_calendar(2000)
        assert cal_1999[_dt.date(1999, 1, 15)] == "成人の日"
        # 2000/1/10 (Mon) が第2月曜
        assert cal_2000[_dt.date(2000, 1, 10)] == "成人の日"


# ── ComputedHolidaySource の制約 ───────────────────────────────────────


class TestComputedSourceConstraints:
    """``ComputedHolidaySource`` の運用上の制約（純粋計算・range 検証）。"""

    def test_computed_does_not_load_requests(self) -> None:
        """``ComputedHolidaySource`` は ``requests`` を import しない（純粋計算）。

        ``requests`` を ``sys.modules`` から抜いた状態でソースを import し、
        ``load()`` を実行しても ``requests`` が読み込まれないことを確認する。
        """
        import sys

        # requests を消してからソースを import
        sys.modules.pop("requests", None)
        from comken.core.holidays.sources.computed import (
            ComputedHolidaySource,
        )

        assert "requests" not in sys.modules, (
            "computed.py は requests を import すべきではない（純粋計算で動くソース）。"
        )

        # load() を呼んでも requests は読まれない
        ComputedHolidaySource(from_year=2026, to_year=2026).load()
        assert "requests" not in sys.modules

    def test_computed_rejects_inverted_range(self) -> None:
        """``from_year > to_year`` は ``ValueError``。"""
        with pytest.raises(ValueError):
            ComputedHolidaySource(from_year=2030, to_year=2020)

    def test_computed_warns_outside_high_precision_range(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """高精度範囲外 (1948-2099) を指定すると WARNING が残る。"""
        with caplog.at_level(logging.WARNING, logger="comken.core.holidays.sources.computed"):
            ComputedHolidaySource(from_year=1940, to_year=2099)
            ComputedHolidaySource(from_year=1948, to_year=2105)
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1
        assert any("高精度" in r.getMessage() for r in warnings)

    def test_computed_default_range_is_1948_to_2099(self) -> None:
        """既定範囲は 1948-2099（タスク仕様）。"""
        source = ComputedHolidaySource()
        holidays = source.load()
        # 範囲内に 1949 年の元日 (1948 は祝日法施行後で祝日なし) が出る
        assert Holiday(date=_dt.date(1949, 1, 1), name="元日") in holidays
        # 範囲内に 2099 年の祝日が複数出る
        assert any(h.date.year == 2099 for h in holidays)
        # 2100 年は出ない（高精度範囲外）
        assert not any(h.date.year == 2100 for h in holidays)


class TestCompanyHolidaySource:
    """``CompanyHolidaySource`` の挙動（会社休日をコード直書きで返す）。"""

    def test_year_end_and_new_year_holiday_default_present(self) -> None:
        """既定で 12/29 - 1/3 が「年末年始休暇」として休業扱いになる。

        12/29, 12/30, 12/31, 1/1, 1/2, 1/3 の 6 日間が ``Holiday`` に
        入ることを確認する。年跨ぎ（12→1）が正しく展開されるかも兼ねる。
        """
        source = CompanyHolidaySource(from_year=2026, to_year=2027)
        holidays = source.load()
        assert Holiday(date=_dt.date(2026, 12, 29), name="年末年始休暇") in holidays
        assert Holiday(date=_dt.date(2026, 12, 30), name="年末年始休暇") in holidays
        assert Holiday(date=_dt.date(2026, 12, 31), name="年末年始休暇") in holidays
        assert Holiday(date=_dt.date(2027, 1, 1), name="年末年始休暇") in holidays
        assert Holiday(date=_dt.date(2027, 1, 2), name="年末年始休暇") in holidays
        assert Holiday(date=_dt.date(2027, 1, 3), name="年末年始休暇") in holidays

    def test_company_holidays_constant_default(self) -> None:
        """既定の ``COMPANY_HOLIDAYS`` は年末年始休暇 (12/29 - 1/3) のみ。"""
        from comken.core.holidays.sources.company import COMPANY_HOLIDAYS

        assert COMPANY_HOLIDAYS == {
            "年末年始休暇": ((12, 29), (12, 30), (12, 31), (1, 1), (1, 2), (1, 3)),
        }

    def test_company_holidays_extra_default_is_empty(self) -> None:
        """既定の ``COMPANY_HOLIDAYS_EXTRA`` は空タプル。"""
        from comken.core.holidays.sources.company import COMPANY_HOLIDAYS_EXTRA

        assert COMPANY_HOLIDAYS_EXTRA == ()

    def test_extra_holidays_named_company_holiday(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``COMPANY_HOLIDAYS_EXTRA`` の名称は「会社休業日」。"""
        from comken.core.holidays.sources import company as company_module

        monkeypatch.setattr(
            company_module,
            "COMPANY_HOLIDAYS_EXTRA",
            (_dt.date(2026, 11, 4),),
        )
        source = company_module.CompanyHolidaySource(from_year=2026, to_year=2026)
        holidays = source.load()
        # ``company_module.Holiday`` を使う: ``comken.core.holidays.Holiday`` と
        # クラス ID が一致しない環境でも比較できるよう、
        # 同じ module から取得した dataclass を使う
        target = company_module.Holiday(date=_dt.date(2026, 11, 4), name="会社休業日")
        assert target in holidays

    def test_rejects_inverted_range(self) -> None:
        """``from_year > to_year`` は ``ValueError``。"""
        with pytest.raises(ValueError):
            CompanyHolidaySource(from_year=2030, to_year=2020)

    def test_is_business_day_false_on_year_end(self) -> None:
        """``CompanyHolidaySource`` 単独でも 12/29 - 1/3 を休業扱いする。"""
        cal = HolidayCalendar.from_sources([CompanyHolidaySource()])
        assert is_business_day(_dt.date(2026, 12, 29), calendar=cal) is False
        assert is_business_day(_dt.date(2027, 1, 3), calendar=cal) is False
        # 12/28 は会社の休業日に登録されていないので、平日なら営業日
        # (2026/12/28 は月曜)
        assert is_business_day(_dt.date(2026, 12, 28), calendar=cal) is True


class TestApproximateHoliday:
    """``Holiday.approximate`` 属性の挙動。

    計算式由来の暫定値（春分の日・秋分の日）だけ ``approximate=True`` を
    付けて、業務フローを止めずに WARNING ログで気づけるようにする。
    """

    def test_default_approximate_is_false(self) -> None:
        """``Holiday`` の ``approximate`` は既定で False。"""
        assert Holiday(date=_dt.date(2026, 1, 1), name="元日").approximate is False

    def test_computed_marks_only_equinox_as_approximate(self) -> None:
        """Computed の春分の日・秋分の日のみ ``approximate=True``。

        固定パターン（ハッピーマンデー・固定日・振替休日・国民の休日）は
        ``approximate=False`` のままで、計算結果として確実なものは警告を出さない。
        """
        holidays = ComputedHolidaySource(from_year=2026, to_year=2026).load()
        for h in holidays:
            if h.name in ("春分の日", "秋分の日"):
                assert h.approximate is True, f"{h} に approximate が付いていません"
            else:
                assert h.approximate is False, f"{h} に approximate が付いています"

    def test_company_holidays_are_not_approximate(self) -> None:
        """``CompanyHolidaySource`` は ``approximate=False`` を維持する。"""
        holidays = CompanyHolidaySource(from_year=2026, to_year=2026).load()
        for h in holidays:
            assert h.approximate is False, f"{h} に approximate が付いています"


class TestCabinetOfficeRefresh:
    """``CabinetOfficeCSVSource.refresh()`` の挙動。"""

    def test_refresh_default_timeout_is_half_second(self) -> None:
        """``refresh()`` は既定で 0.5 秒タイムアウト（業務フローを止めないため）。"""
        assert CabinetOfficeCSVSource()._refresh_timeout == 0.5

    def test_refresh_returns_holidays_on_success(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """``refresh()`` は内閣府取得に成功すると ``Holiday`` のリストを返しキャッシュへ書く。"""
        source = CabinetOfficeCSVSource(cache_path=tmp_path / "syukujitsu.csv")
        # fixture のバイト列を返す
        fresh_bytes = FIXTURE_PATH.read_bytes()
        monkeypatch.setattr(source, "_download", lambda timeout=None: fresh_bytes)

        holidays = source.refresh()

        assert any(h.name == "元日" for h in holidays)
        # キャッシュに書かれている
        assert (tmp_path / "syukujitsu.csv").exists()

    def test_refresh_falls_back_to_cache_on_fetch_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """内閣府取得失敗時にキャッシュがあれば警告ログを出してキャッシュで代用。"""
        from comken.exceptions import HolidayCalendarFetchError

        cache_path = tmp_path / "syukujitsu.csv"
        cache_path.write_bytes(FIXTURE_PATH.read_bytes())
        source = CabinetOfficeCSVSource(cache_path=cache_path)

        def fail(timeout: float | None = None) -> bytes:
            raise HolidayCalendarFetchError("https://example/", "timeout")

        monkeypatch.setattr(source, "_download", fail)

        holidays = source.refresh()

        assert any(h.name == "元日" for h in holidays)


class TestHolidayCalendarCascade:
    """``HolidayCalendar.from_sources()`` のカスケード動作。"""

    def test_cabinet_office_failure_falls_back_to_computed(self) -> None:
        """内閣府失敗 → Computed にフォールバック（カスケード）。

        オフライン BO 環境で内閣府が取得できなくても、Computed が
        固定パターンの祝日を返すため業務が止まらない。
        """
        from comken.exceptions import HolidayCalendarFetchError

        class FailingCabinet:
            def load(self):
                raise HolidayCalendarFetchError("https://example/", "network")

        calendar = HolidayCalendar.from_sources(
            [
                FailingCabinet(),
                ComputedHolidaySource(from_year=2026, to_year=2026),
            ]
        )

        # Computed の固定パターンの祝日が反映されている
        assert any(h.name == "憲法記念日" for h in calendar.all_holidays())

    def test_all_sources_failure_raises_last_error(self) -> None:
        """全 source が失敗したら最後の ``HolidayCalendarFetchError`` を送出。"""
        from comken.exceptions import HolidayCalendarFetchError

        class Failing:
            def load(self):
                raise HolidayCalendarFetchError("https://example/", "fail")

        with pytest.raises(HolidayCalendarFetchError):
            HolidayCalendar.from_sources([Failing(), Failing()])


class TestHolidayCalendarRefresh:
    """``HolidayCalendar.is_holiday()`` の内閣府強制再取得と approximate 警告。"""

    def test_is_holiday_calls_refresh_for_current_year(self) -> None:
        """ターゲットが今年のとき内閣府 refresh を試みる。"""
        called = {"count": 0}

        class FakeCabinet:
            def refresh(self):
                called["count"] += 1
                return []

            def load(self):
                return []

        calendar = HolidayCalendar.from_sources(
            [
                FakeCabinet(),
                ComputedHolidaySource(from_year=2026, to_year=2026),
            ]
        )
        this_year = _dt.date.today().year  # noqa: DTZ011
        calendar.is_holiday(_dt.date(this_year, 1, 1))
        assert called["count"] >= 1

    def test_is_holiday_does_not_refresh_for_old_year(self) -> None:
        """去年以前は refresh を試まない（内閣府 CSV には無いはずなので）。"""
        called = {"count": 0}

        class FakeCabinet:
            def refresh(self):
                called["count"] += 1
                return []

            def load(self):
                return []

        calendar = HolidayCalendar.from_sources(
            [
                FakeCabinet(),
                ComputedHolidaySource(from_year=2026, to_year=2026),
            ]
        )
        calendar.is_holiday(_dt.date(2020, 1, 1))  # 2020 年（過去）
        assert called["count"] == 0

    def test_is_holiday_warns_on_approximate(self, caplog: pytest.LogCaptureFixture) -> None:
        """``approximate=True`` の Holiday を返すときに WARNING ログが出る。

        春分の日・秋分の日は内閣府発表と ±1 日前後する可能性があるので、
        ユーザーに気づかせる。
        """
        calendar = HolidayCalendar.from_sources(
            [
                ComputedHolidaySource(from_year=2026, to_year=2026),
            ]
        )
        # 春分の日 (approximate=True)
        with caplog.at_level(logging.WARNING, logger="comken.core.holidays.calendar"):
            calendar.is_holiday(_dt.date(2026, 3, 20))
        assert any("計算式による暫定値" in r.getMessage() for r in caplog.records)

    def test_refresh_only_once_per_year(self) -> None:
        """同じ年には 1 回しか refresh を試まない（重複防止）。"""
        called = {"count": 0}

        class FakeCabinet:
            def refresh(self):
                called["count"] += 1
                return []

            def load(self):
                return []

        calendar = HolidayCalendar.from_sources(
            [
                FakeCabinet(),
                ComputedHolidaySource(from_year=2026, to_year=2026),
            ]
        )
        this_year = _dt.date.today().year  # noqa: DTZ011
        calendar.is_holiday(_dt.date(this_year, 1, 1))
        calendar.is_holiday(_dt.date(this_year, 6, 15))
        calendar.is_holiday(_dt.date(this_year, 12, 31))
        assert called["count"] == 1


# ── 既定カレンダー ─────────────────────────────────────────────────────


class TestDefaultCalendar:
    """``default_calendar`` / ``set_default_calendar`` の挙動。

    ``_default_calendar`` はモジュールグローバルなので、テスト間で
    リークしないよう ``setup_method`` で必ず ``None`` にリセットする。
    """

    def setup_method(self) -> None:
        """各テスト開始時に ``_default_calendar`` をリセットする。"""
        set_default_calendar(None)

    def teardown_method(self) -> None:
        """テスト後に ``_default_calendar`` をリセットし、次のテストへ漏らさない。"""
        set_default_calendar(None)

    def test_default_calendar_does_not_use_requests(self) -> None:
        """既定カレンダーがネットワークに出ないこと（``requests`` を import しない）。

        ``CabinetOfficeCSVSource`` は ``requests`` 依存なので、これが既定
        カレンダーに含まれていないことの間接チェック。
        """
        import sys

        sys.modules.pop("requests", None)
        default_calendar()
        assert "requests" not in sys.modules, (
            "既定カレンダーの生成で requests が import されました。"
            "CabinetOfficeCSVSource を含めてはいけません。"
        )

    def test_default_calendar_includes_company_holidays(self) -> None:
        """既定カレンダーは ``CompanyHolidaySource`` を含む（年末年始休暇）。

        既定カレンダーだけで ``is_business_day(2026/12/29)`` が ``False``
        になることを確認する。
        """
        assert is_business_day(_dt.date(2026, 12, 29)) is False
        assert is_business_day(_dt.date(2027, 1, 3)) is False

    def test_set_default_calendar_swaps_calendar(self) -> None:
        """``set_default_calendar`` で差し替えられる。"""
        custom = HolidayCalendar([Holiday(date=_dt.date(2024, 1, 1), name="元日")])
        set_default_calendar(custom)
        assert is_business_day(_dt.date(2024, 1, 1)) is False  # 元日は非営業日
        assert is_business_day(_dt.date(2024, 1, 2)) is True  # 火曜は営業日

    def test_set_default_calendar_none_resets(self) -> None:
        """``None`` を渡すと既定の遅延生成に戻る（次回 ``default_calendar()`` で再生成）。"""
        custom = HolidayCalendar([])
        set_default_calendar(custom)
        # 空カレンダーは祝日が無いので、平日（2024/1/1 月）は営業日になる
        assert is_business_day(_dt.date(2024, 1, 1)) is True
        # リセット後の遅延生成では、同梱 CSV + Computed + Company が効く（2024/1/1 は元日）
        set_default_calendar(None)
        assert is_business_day(_dt.date(2024, 1, 1)) is False

    def test_module_functions_use_default_calendar(self) -> None:
        """``is_business_day`` 等のモジュール関数が ``calendar=None`` で既定カレンダーを使う。"""
        # 既定カレンダーが 2026/5/3 と 2026/5/6 を祝日扱いするかをチェック
        # （2026/5/3 は日曜・憲法記念日、5/6 は水曜・振替休日）
        assert is_business_day(_dt.date(2026, 5, 3)) is False
        assert is_business_day(_dt.date(2026, 5, 6)) is False
        assert is_business_day(_dt.date(2026, 5, 7)) is True  # 木、平日

    def test_module_functions_respect_explicit_calendar(self) -> None:
        """``calendar=...`` を明示したときは既定カレンダーではなくそれが使われる。"""
        # 祝日を 1 件も持たない空カレンダーは、すべて「非祝日」扱い
        empty = HolidayCalendar([])
        assert is_business_day(_dt.date(2024, 1, 1), calendar=empty) is True
        assert business_day_on_or_after(_dt.date(2024, 1, 1), calendar=empty) == _dt.date(
            2024, 1, 1
        )


def _bundled_calendar() -> HolidayCalendar:
    """同梱の ``syukujitsu.csv`` から組み立てた ``HolidayCalendar``。

    テスト fixture は業務で使う範囲を抜粋した小さなものだが、
    ゴールデンウィークのように「複数日が連なって休業」するケースを
    検証するには収録範囲が足りない。``comken/core/holidays/data/syukujitsu.csv``
    には 2027 年までの完全な祝日が収録されているので、
    「実カレンダー通り」の挙動を確かめるときはこれを使う。
    """
    bundled = (
        Path(__file__).parent.parent / "comken" / "core" / "holidays" / "data" / "syukujitsu.csv"
    )
    return HolidayCalendar.from_csv(bundled)


class TestCalendarBoundOn2026May:
    """2026 年 5 月（GW を含む月）での business_day_after / on_or_after の対比。

    5/3 (Sun) 憲法記念日 → 5/4 (Mon) みどりの日 → 5/5 (Tue) こどもの日 →
    5/6 (Wed) 振替休日 → 5/7 (Thu) 平日、という並び。
    """

    def test_business_day_after_from_may_3(self) -> None:
        """``business_day_after(2026/5/3)`` は 5/7 を返す（5/3 自身は含まない）。"""
        cal = _bundled_calendar()
        assert business_day_after(_dt.date(2026, 5, 3), calendar=cal) == _dt.date(2026, 5, 7)

    def test_business_day_on_or_after_from_may_3(self) -> None:
        """``business_day_on_or_after(2026/5/3)`` は GW 後の 5/7 を返す（5/3 は祝日）。"""
        cal = _bundled_calendar()
        assert business_day_on_or_after(_dt.date(2026, 5, 3), calendar=cal) == _dt.date(2026, 5, 7)

    def test_business_day_after_from_weekday_uses_next(self) -> None:
        """``business_day_after(2026/5/1 金曜)`` は 5/7 木曜（5/3-5/6 を含めて飛ばす）。"""
        cal = _bundled_calendar()
        assert business_day_after(_dt.date(2026, 5, 1), calendar=cal) == _dt.date(2026, 5, 7)

    def test_business_day_on_or_after_from_weekday_returns_target(self) -> None:
        """``business_day_on_or_after(2026/5/1 金曜)`` は 5/1 そのものを返す。"""
        cal = _bundled_calendar()
        assert business_day_on_or_after(_dt.date(2026, 5, 1), calendar=cal) == _dt.date(2026, 5, 1)


class TestModuleFunctionsFromCore:
    """``comken.core`` から再エクスポートされた同名関数の挙動。"""

    def setup_method(self) -> None:
        """既定カレンダーがテストごとにリセットされるよう、``None`` で初期化。"""
        set_default_calendar(None)

    def teardown_method(self) -> None:
        set_default_calendar(None)

    def test_core_reexports_match_calendar_module(self) -> None:
        """``comken.core`` から ``is_business_day`` などを取って既定カレンダーで動く。

        既定カレンダーは同梱 CSV を使うので、ゴールデンウィークを含む 2026/5 で
        検算できる。
        """
        from comken.core import is_business_day as core_is_business_day
        from comken.core import last_business_day_of_month as core_last
        from comken.core import nth_business_day_of_month as core_nth

        assert core_is_business_day(_dt.date(2026, 5, 3)) is False  # 日曜・祝日
        assert core_last(_dt.date(2026, 5, 1)) == _dt.date(2026, 5, 29)
        assert core_nth(_dt.date(2026, 5, 1), 3) == _dt.date(2026, 5, 8)

    def test_business_day_on_or_before_15th(self) -> None:
        """「15日、休みならその前の営業日」の例（``business_day_on_or_before``）。"""
        cal = _bundled_calendar()
        # 2026/5/15 は金曜で祝日でもなく、そのまま返る
        assert business_day_on_or_before(_dt.date(2026, 5, 15), calendar=cal) == _dt.date(
            2026, 5, 15
        )
        # 2026/5/16 (土) → 前の営業日 = 2026/5/15 (金)
        assert business_day_on_or_before(_dt.date(2026, 5, 16), calendar=cal) == _dt.date(
            2026, 5, 15
        )


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

        assert month_end(_dt.date(2026, 5, 15)) == _dt.date(2026, 5, 31)  # 31 日
        assert month_end(_dt.date(2026, 4, 15)) == _dt.date(2026, 4, 30)  # 30 日
        assert month_end(_dt.date(2024, 2, 15)) == _dt.date(2024, 2, 29)  # 閏年 29 日
        assert month_end(_dt.date(2025, 2, 15)) == _dt.date(2025, 2, 28)  # 平年 28 日


# ── 営業日オフセット計算（モジュール関数）─────────────────────


class TestBusinessDayOffsets:
    """``business_day_after`` / ``business_day_before`` /
    ``business_day_on_or_after`` / ``business_day_on_or_before`` の挙動。
    """

    def test_after_excludes_target(self) -> None:
        """``business_day_after`` は ``target`` 自身を含まない（営業日でも翌日）。"""
        cal = HolidayCalendar([])
        # 2024-05-06 は月曜で営業日 → business_day_after は 5/7 火
        assert business_day_after(_dt.date(2024, 5, 6), calendar=cal) == _dt.date(2024, 5, 7)

    def test_on_or_after_includes_target(self) -> None:
        """``business_day_on_or_after`` は ``target`` が営業日ならそのまま返す。"""
        cal = HolidayCalendar([])
        # 2024-05-06 は営業日なのでそのまま
        assert business_day_on_or_after(_dt.date(2024, 5, 6), calendar=cal) == _dt.date(2024, 5, 6)

    def test_after_vs_on_or_after_when_target_is_business_day(self) -> None:
        """営業日を渡したとき、前者は翌日・後者はその日自身を返す。"""
        cal = HolidayCalendar([])
        d = _dt.date(2024, 5, 6)  # 月曜・営業日
        assert business_day_after(d, calendar=cal) == _dt.date(2024, 5, 7)
        assert business_day_on_or_after(d, calendar=cal) == _dt.date(2024, 5, 6)

    def test_before_excludes_target(self) -> None:
        """``business_day_before`` は ``target`` 自身を含まない（営業日でも前日）。"""
        cal = HolidayCalendar([])
        # 2024-05-06 は月曜で営業日 → business_day_before は 5/3 金
        assert business_day_before(_dt.date(2024, 5, 6), calendar=cal) == _dt.date(2024, 5, 3)

    def test_on_or_before_includes_target(self) -> None:
        """``business_day_on_or_before`` は ``target`` が営業日ならそのまま返す。"""
        cal = HolidayCalendar([])
        assert business_day_on_or_before(_dt.date(2024, 5, 6), calendar=cal) == _dt.date(2024, 5, 6)

    def test_before_vs_on_or_before_when_target_is_business_day(self) -> None:
        """営業日を渡したとき、前者は前日・後者はその日自身を返す。"""
        cal = HolidayCalendar([])
        d = _dt.date(2024, 5, 6)
        assert business_day_before(d, calendar=cal) == _dt.date(2024, 5, 3)
        assert business_day_on_or_before(d, calendar=cal) == _dt.date(2024, 5, 6)

    def test_on_or_after_skips_holiday(self) -> None:
        """``target`` が祝日のとき、``on_or_after`` は翌日以降を探す。"""
        cal = HolidayCalendar([Holiday(_dt.date(2024, 5, 6), "架空の祝日")])
        # 2024-05-06 は月曜だが祝日扱いにした架空カレンダー
        assert business_day_on_or_after(_dt.date(2024, 5, 6), calendar=cal) == _dt.date(2024, 5, 7)

    def test_module_functions_delegate_to_private_methods(self) -> None:
        """同名モジュール関数は ``HolidayCalendar`` のプライベートメソッドに委譲する。"""
        cal = HolidayCalendar([])
        d = _dt.date(2024, 5, 6)
        assert business_day_after(d, calendar=cal) == cal._business_day_after(d)
        assert business_day_before(d, calendar=cal) == cal._business_day_before(d)
        assert business_day_on_or_after(d, calendar=cal) == cal._business_day_on_or_after(d)
        assert business_day_on_or_before(d, calendar=cal) == cal._business_day_on_or_before(d)

    def test_module_functions_require_keyword_calendar(self) -> None:
        """``calendar`` はキーワード専用（位置引数だと TypeError）。"""
        cal = HolidayCalendar([])
        with pytest.raises(TypeError):
            business_day_after(_dt.date(2024, 5, 6), cal)  # type: ignore[misc]


class TestNthBusinessDayOfMonth:
    """``nth_business_day_of_month`` の挙動（祝土日をまたぐ月で検証）。"""

    def test_returns_nth_business_day(self) -> None:
        """月の第 ``n`` 営業日を返す。"""
        cal = HolidayCalendar([])
        # 2024-05 の営業日（土日祝を飛ばした最初の 3 日）:
        # 5/1(水), 5/2(木), 5/3(金) → 第 3 営業日は 5/3
        assert nth_business_day_of_month(_dt.date(2024, 5, 15), 3, calendar=cal) == _dt.date(
            2024, 5, 3
        )

    def test_returns_nth_business_day_skipping_holidays(self) -> None:
        """祝土日をまたぐ月の第 ``n`` 営業日を返す。"""
        # 5/3〜5/6 を全部祝日にした月 → 営業日は 5/1(水), 5/2(木), 5/7(火), 5/8(水), ...
        cal = HolidayCalendar(
            [
                Holiday(_dt.date(2024, 5, 3), "憲法"),
                Holiday(_dt.date(2024, 5, 4), "みどり"),
                Holiday(_dt.date(2024, 5, 5), "こどもの日"),
                Holiday(_dt.date(2024, 5, 6), "振替"),
            ]
        )
        assert nth_business_day_of_month(_dt.date(2024, 5, 15), 3, calendar=cal) == _dt.date(
            2024, 5, 7
        )

    def test_returns_first_business_day(self) -> None:
        """``n == 1`` でその月の最初の営業日を返す。"""
        cal = HolidayCalendar([])
        # 2024-05-01 は水曜で祝日ではないのでそのまま
        assert nth_business_day_of_month(_dt.date(2024, 5, 15), 1, calendar=cal) == _dt.date(
            2024, 5, 1
        )

    def test_raises_when_n_exceeds_month_business_days(self) -> None:
        """``n`` が月の営業日数を超えると ``BusinessDayNotFoundError``。"""
        # 1ヶ月全部祝日に → 営業日は 0 件
        march = [Holiday(_dt.date(2024, 3, d), f"holiday{d}") for d in range(1, 32)]
        cal = HolidayCalendar(march)
        with pytest.raises(BusinessDayNotFoundError):
            nth_business_day_of_month(_dt.date(2024, 3, 15), 1, calendar=cal)

    def test_raises_when_n_is_less_than_one(self) -> None:
        """``n < 1`` で ``BusinessDayNotFoundError``。"""
        cal = HolidayCalendar([])
        with pytest.raises(BusinessDayNotFoundError):
            nth_business_day_of_month(_dt.date(2024, 5, 15), 0, calendar=cal)
        with pytest.raises(BusinessDayNotFoundError):
            nth_business_day_of_month(_dt.date(2024, 5, 15), -1, calendar=cal)

    def test_module_function_delegates(self) -> None:
        """同名モジュール関数はプライベートメソッドに委譲する。"""
        cal = HolidayCalendar([])
        d = _dt.date(2024, 5, 15)
        assert nth_business_day_of_month(d, 3, calendar=cal) == cal._nth_business_day_of_month(d, 3)


class TestFirstAndLastBusinessDayOfMonth:
    """``first_business_day_of_month`` / ``last_business_day_of_month`` の挙動。"""

    def test_last_business_day_when_month_end_is_weekend(self) -> None:
        """月末が土日のとき、直前の営業日に遡る。"""
        cal = HolidayCalendar([])
        # 2024-08-31 は土曜 → 8/30 (金)
        assert last_business_day_of_month(_dt.date(2024, 8, 20), calendar=cal) == _dt.date(
            2024, 8, 30
        )

    def test_last_business_day_when_month_end_is_sunday(self) -> None:
        """月末が日曜のとき、金曜に戻る。"""
        cal = HolidayCalendar([])
        # 2024-06-30 は日曜 → 6/28 (金)
        assert last_business_day_of_month(_dt.date(2024, 6, 15), calendar=cal) == _dt.date(
            2024, 6, 28
        )

    def test_last_business_day_when_month_end_is_holiday(self) -> None:
        """月末が祝日のとき、直前の営業日に遡る。"""
        # 2024-04-30 は火曜で祝日に → 直前は 4/29 (月、祝日カレンダーにないので営業日)
        cal = HolidayCalendar([Holiday(_dt.date(2024, 4, 30), "月末祝日")])
        assert last_business_day_of_month(_dt.date(2024, 4, 15), calendar=cal) == _dt.date(
            2024, 4, 29
        )

    def test_first_business_day_when_month_start_is_weekend(self) -> None:
        """月初が土日のとき、最初の営業日に進む。"""
        cal = HolidayCalendar([])
        # 2024-09-01 は日曜 → 9/2 (月)
        assert first_business_day_of_month(_dt.date(2024, 9, 15), calendar=cal) == _dt.date(
            2024, 9, 2
        )

    def test_first_business_day_when_month_start_is_event(self) -> None:
        """月初が祝日のとき、最初の営業日に進む。"""
        # 2024-05-01 は水曜だが架空カレンダーで祝日に
        cal = HolidayCalendar([Holiday(_dt.date(2024, 5, 1), "メーデー（架空）")])
        assert first_business_day_of_month(_dt.date(2024, 5, 15), calendar=cal) == _dt.date(
            2024, 5, 2
        )

    def test_month_with_no_business_days_raises(self) -> None:
        """前後に ``BUSINESS_DAY_SEARCH_LIMIT`` を超える祝日がある月では例外。

        月の前後にも祝日が無いと、``last_business_day`` は過去方向に探索して
        範囲外（祝日の前）に出てしまい、誤って「営業日」を返してしまう。
        ここでは月初と月末の**両方向**で上限到達するよう、月を挟む長期間の
        祝日データを用意する。
        """
        from comken.core.holidays import (
            BUSINESS_DAY_SEARCH_LIMIT,
        )

        # 2023/1/1 から 2025/12/31 まで (= 約 3 年分) を全部祝日にして、
        # どちら向きに探索しても上限到達するようにする。
        span_days = (_dt.date(2025, 12, 31) - _dt.date(2023, 1, 1)).days + 1
        assert span_days > BUSINESS_DAY_SEARCH_LIMIT * 2
        long_holidays = [
            Holiday(_dt.date(2023, 1, 1) + _dt.timedelta(days=i), f"holiday{i}")
            for i in range(span_days)
        ]
        cal = HolidayCalendar(long_holidays)
        with pytest.raises(BusinessDayNotFoundError):
            first_business_day_of_month(_dt.date(2024, 3, 15), calendar=cal)
        with pytest.raises(BusinessDayNotFoundError):
            last_business_day_of_month(_dt.date(2024, 3, 15), calendar=cal)

    def test_module_functions_delegate(self) -> None:
        """同名モジュール関数はプライベートメソッドに委譲する。"""
        cal = HolidayCalendar([])
        d = _dt.date(2024, 8, 20)
        assert first_business_day_of_month(d, calendar=cal) == cal._first_business_day_of_month(d)
        assert last_business_day_of_month(d, calendar=cal) == cal._last_business_day_of_month(d)


class TestAddBusinessDays:
    """``add_business_days`` の挙動。"""

    def test_zero_returns_target_unchanged(self) -> None:
        """``n == 0`` は ``target`` をそのまま返す（休日でも）。"""
        cal = HolidayCalendar([Holiday(_dt.date(2024, 1, 1), name="元日")])
        holiday_target = _dt.date(2024, 1, 1)
        # 休日を渡してもそのまま返る（Excel WORKDAY と同じ挙動）
        assert add_business_days(holiday_target, 0, calendar=cal) == holiday_target

    def test_positive_one_returns_business_day_after_target(self) -> None:
        """``n == 1`` で ``target`` が営業日でも**翌営業日**を返す（Excel WORKDAY 互換）。

        「翌営業日」と「1 営業日後」は別物: 前者は ``business_day_after``、
        後者は ``add_business_days(d, 1)``。後者は「今日から 1 営業日進め」と
        解釈するので ``target`` 自身は結果に含めない。
        """
        cal = HolidayCalendar([Holiday(_dt.date(2024, 1, 1), name="元日")])
        # 2024-01-02 (火、営業日) + 1 営業日 → 1/3 (水)
        assert add_business_days(_dt.date(2024, 1, 2), 1, calendar=cal) == _dt.date(2024, 1, 3)

    def test_positive_skips_weekend_and_holiday(self) -> None:
        """``n > 0`` で営業日単位に進む。"""
        cal = HolidayCalendar([Holiday(_dt.date(2024, 1, 1), name="元日")])
        # 2024-01-02 から 1 営業日後 → 1/3 (水)
        assert add_business_days(_dt.date(2024, 1, 2), 1, calendar=cal) == _dt.date(2024, 1, 3)
        # 2 営業日後 → 1/4 (木)
        assert add_business_days(_dt.date(2024, 1, 2), 2, calendar=cal) == _dt.date(2024, 1, 4)

    def test_positive_skips_holiday_chain(self) -> None:
        """祝日が連続しているとき、営業日まで正しく飛ぶ。"""
        cal = HolidayCalendar([Holiday(_dt.date(2024, 1, 8), name="成人の日（架空）")])
        # 2024-01-05 (金) + 1 営業日 → 1/9 (火、成人の日(架空)を飛ばす)
        assert add_business_days(_dt.date(2024, 1, 5), 1, calendar=cal) == _dt.date(2024, 1, 9)
        # 2024-01-05 (金) + 2 営業日 → 1/10 (水)
        assert add_business_days(_dt.date(2024, 1, 5), 2, calendar=cal) == _dt.date(2024, 1, 10)

    def test_negative_returns_previous_business_days(self) -> None:
        """``n < 0`` で ``|n|`` 営業日前に戻る。"""
        cal = HolidayCalendar([Holiday(_dt.date(2024, 1, 1), name="元日")])
        # 2024-01-10 (水) の -1 営業日 → 1/9 (火)
        assert add_business_days(_dt.date(2024, 1, 10), -1, calendar=cal) == _dt.date(2024, 1, 9)
        # 2024-01-10 (水) の -2 営業日 → 1/8 (月)
        assert add_business_days(_dt.date(2024, 1, 10), -2, calendar=cal) == _dt.date(2024, 1, 8)

    def test_module_function_delegates(self) -> None:
        """同名モジュール関数はプライベートメソッドに委譲する。"""
        cal = HolidayCalendar([])
        d = _dt.date(2024, 1, 10)
        assert add_business_days(d, 2, calendar=cal) == cal._add_business_days(d, 2)


class TestBusinessDaySearchLimit:
    """探索上限 400 日で ``BusinessDayNotFoundError`` になることを確認。"""

    def test_raises_after_search_limit_when_all_days_are_holidays(self) -> None:
        """全日が祝日のカレンダーで ``business_day_after`` が上限到達で例外。"""
        from comken.core.holidays import BUSINESS_DAY_SEARCH_LIMIT

        # 探索上限 (BUSINESS_DAY_SEARCH_LIMIT) を超える祝日にして、
        # ``business_day_after`` の探索が必ず上限到達するようにする。
        holidays = [
            Holiday(_dt.date(2025, 1, 1) + _dt.timedelta(days=i), f"holiday{i}")
            for i in range(BUSINESS_DAY_SEARCH_LIMIT + 100)
        ]
        cal = HolidayCalendar(holidays)
        with pytest.raises(BusinessDayNotFoundError):
            business_day_after(_dt.date(2025, 1, 1), calendar=cal)
        # 上限が想定どおり（テストの前提）
        assert BUSINESS_DAY_SEARCH_LIMIT == 400
