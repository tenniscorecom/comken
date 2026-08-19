"""comken.toolbox.holidays のテスト。

内閣府の祝日 CSV（CP932 エンコード）・社内管理表（Excel）・
ソース Protocol の各経路を横断的に検証する。
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import logging
from pathlib import Path

import pytest

from comken.exceptions import (
    HolidayCalendarError,
    HolidayCalendarExpiredError,
    HolidayCalendarFetchError,
    HolidayCalendarFormatError,
    HolidayCalendarSourceError,
)
from comken.toolbox.holidays import (
    CabinetOfficeCsvSource,
    ComkenMasterTableSource,
    ComputedHolidaySource,
    Holiday,
    HolidayCalendar,
    HolidaySource,
    is_business_day,
)

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
        from comken.toolbox.holidays.csv_source import load_cabinet_office_csv

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
        from comken.toolbox.holidays.csv_source import load_cabinet_office_csv

        missing = tmp_path / "nope.csv"
        with pytest.raises(HolidayCalendarFormatError):
            load_cabinet_office_csv(missing)

    def test_garbage_text_raises_format_error(self, tmp_path: Path) -> None:
        """日付として読めない文字列だけだと ``HolidayCalendarFormatError``。"""
        from comken.toolbox.holidays.csv_source import load_cabinet_office_csv

        bad = tmp_path / "bad.csv"
        bad.write_text("hello,world\nfoo,bar\n", encoding="cp932")
        with pytest.raises(HolidayCalendarFormatError):
            load_cabinet_office_csv(bad)

    def test_wrong_encoding_raises_format_error(self, tmp_path: Path) -> None:
        """CP932 以外の文字コードで書かれたものは読めない（FormatError）。"""
        from comken.toolbox.holidays.csv_source import load_cabinet_office_csv

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
        assert cal.is_business_day(_dt.date(2024, 1, 2)) is True  # 火曜

    def test_weekday_holiday_is_not_business_day(self) -> None:
        """祝日の月曜は営業日ではない。"""
        cal = _fixture_calendar()
        assert cal.is_business_day(_dt.date(2024, 1, 1)) is False

    def test_saturday_is_skipped_by_default(self) -> None:
        """土曜は ``skip_weekends=True``（既定）で休業。"""
        cal = _fixture_calendar()
        assert cal.is_business_day(_dt.date(2024, 1, 6)) is False  # 土曜

    def test_sunday_is_skipped_by_default(self) -> None:
        """日曜は ``skip_weekends=True``（既定）で休業。"""
        cal = _fixture_calendar()
        assert cal.is_business_day(_dt.date(2024, 1, 7)) is False  # 日曜

    def test_saturday_is_business_when_skip_weekends_false(self) -> None:
        """``skip_weekends=False`` なら土曜でも祝日でなければ営業日。"""
        cal = _fixture_calendar()
        assert cal.is_business_day(_dt.date(2024, 1, 6), skip_weekends=False) is True

    def test_holiday_saturday_still_not_business(self) -> None:
        """土曜でも祝日なら ``False``（``skip_weekends=False`` でも）。"""
        cal = _fixture_calendar()
        # 2024-05-04 は土曜かつ祝日（みどりの日）
        assert cal.is_business_day(_dt.date(2024, 5, 4), skip_weekends=False) is False


class TestNextBusinessDay:
    """``next_business_day`` の挙動。"""

    def test_skips_weekend_and_holiday(self) -> None:
        """週末と祝日の両方を飛ばす。"""
        cal = _fixture_calendar()
        # 2024-05-02 は木曜 → 翌営業は 2024-05-06（月）= 5/3,4,5 を飛ばす
        assert cal.next_business_day(_dt.date(2024, 5, 2)) == _dt.date(2024, 5, 6)

    def test_skips_only_holiday_when_target_is_weekday(self) -> None:
        """``target`` が平日のとき、祝日だけ飛ばす。"""
        cal = _fixture_calendar()
        # 2024-04-30 は火曜 → 4/29 が昭和の日（祝）で、5/1 は祝日ではないので 5/1 が翌営業
        assert cal.next_business_day(_dt.date(2024, 4, 30)) == _dt.date(2024, 5, 1)

    def test_next_business_day_respects_skip_weekends_flag(self) -> None:
        """``skip_weekends=False`` でも翌日が祝日なら飛ばす。"""
        cal = _fixture_calendar()
        # 2024-01-01 は祝日かつ月曜 → 翌営業は 2024-01-02 の火曜
        assert cal.next_business_day(_dt.date(2024, 1, 1), skip_weekends=False) == _dt.date(
2024, 1, 2
        )


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
        cal = HolidayCalendar(
            [Holiday(date=_dt.date(2024, 5, 5), name="こどもの日")]
        )
        today = _dt.date(2024, 4, 20)  # 残り 15 日
        with caplog.at_level(logging.WARNING, logger="comken.toolbox.holidays.calendar"):
            cal.is_business_day(today)
            cal.is_business_day(today)  # 2回呼んでも 1度だけ
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "15" in warnings[0].getMessage()

    def test_warning_not_logged_when_far_from_expiry(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """30日以上先なら警告は出ない。"""
        cal = HolidayCalendar(
            [Holiday(date=_dt.date(2025, 5, 5), name="こどもの日")]
        )
        today = _dt.date(2024, 1, 1)
        with caplog.at_level(logging.WARNING, logger="comken.toolbox.holidays.calendar"):
            cal.is_business_day(today)
        assert not [r for r in caplog.records if r.levelno == logging.WARNING]

    def test_warning_not_repeated_on_next_day(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """翌日にもう一度 ``is_business_day`` を呼ぶと、その日では 1度だけ出る。"""
        cal = HolidayCalendar(
            [Holiday(date=_dt.date(2024, 5, 5), name="こどもの日")]
        )
        with caplog.at_level(logging.WARNING, logger="comken.toolbox.holidays.calendar"):
            cal.is_business_day(_dt.date(2024, 4, 20))  # 残り 15 日 → 警告
            cal.is_business_day(_dt.date(2024, 4, 21))  # 残り 14 日 → 警告（この日では 1度目）
            cal.is_business_day(_dt.date(2024, 4, 21))  # 2度目（同じ日）→ 出ない
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 2


# ── from_sources / マージ ──────────────────────────────────────────────


class TestFromSources:
    """``HolidayCalendar.from_sources`` のマージ動作。"""

    def test_merges_multiple_sources(self) -> None:
        """複数の ``HolidaySource`` を 1つのカレンダーにまとめられる。"""
        from comken.toolbox.holidays.csv_source import parse_cabinet_office_text

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

    def test_first_source_wins_on_duplicate_date(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """同じ日付が複数のソースにあるとき、先勝ち + 警告ログ。"""
        from comken.toolbox.holidays.csv_source import parse_cabinet_office_text

        sample_a = "国民の祝日・休日月日,国民の祝日・休日名称\n2024-01-01,元日（内閣府）\n"
        sample_b = "国民の祝日・休日月日,国民の祝日・休日名称\n2024-01-01,元日（管理表）\n"

        class _InlineSource:
            def __init__(self, text: str) -> None:
                self._text = text

            def load(self) -> list[Holiday]:
                return parse_cabinet_office_text(self._text, source="inline")

        with caplog.at_level(logging.WARNING, logger="comken.toolbox.holidays.calendar"):
            cal = HolidayCalendar.from_sources(
                [_InlineSource(sample_a), _InlineSource(sample_b)]
            )
        names = tuple(cal.holiday_names(_dt.date(2024, 1, 1)))
        # 先勝ちなので「内閣府」の名称が残る
        assert names == ("元日（内閣府）",)
        # 警告ログが出ている
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("重複" in r.getMessage() for r in warnings)


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
        """``HolidayCalendar.is_business_day`` に委譲する。"""
        cal = _fixture_calendar()
        assert (
            is_business_day(_dt.date(2024, 1, 2), calendar=cal)
            == cal.is_business_day(_dt.date(2024, 1, 2))
        )
        # 祝日側は ``False``
        assert is_business_day(_dt.date(2024, 1, 1), calendar=cal) is False

    def test_calendar_is_keyword_only(self) -> None:
        """``calendar`` はキーワード専用。位置引数だとエラー。"""
        cal = _fixture_calendar()
        with pytest.raises(TypeError):
            is_business_day(_dt.date(2024, 1, 2), cal)  # type: ignore[misc]


# ── CabinetOfficeCsvSource ────────────────────────────────────────────────


class _StubResponse:
    """requests のレスポンスを模倣する最小スタブ。"""

    def __init__(self, content: bytes, status_code: int = 200) -> None:
        self.content = content
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")


class TestCabinetOfficeCsvSource:
    """``CabinetOfficeCsvSource`` のキャッシュ・TTL・フェッチ失敗フォールバック。"""

    def test_uses_cache_when_fresh(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """TTL 内ならキャッシュをそのまま使う（ダウンロードを呼ばない）。"""
        cache = tmp_path / "cache.csv"
        cache.write_bytes("国民の祝日・休日月日,国民の祝日・休日名称\n2024-01-01,元日\n".encode("cp932"))
        # mtime を今に更新
        import os

        os.utime(
            cache,
            (_dt.datetime.now().timestamp(), _dt.datetime.now().timestamp()),  # noqa: DTZ005  # os.utime は naive を渡す
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

        source = CabinetOfficeCsvSource(cache_path=cache, ttl_seconds=60)
        holidays = list(source.load())
        assert called["count"] == 0, "キャッシュが fresh ならリクエストを呼ばない"
        assert holidays[0].name == "元日"

    def test_downloads_when_cache_stale(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TTL を過ぎていたらダウンロードしてキャッシュを更新する。"""
        cache = tmp_path / "cache.csv"
        cache.write_bytes(b"stale")
        import os

        # 昔 (2000年) の mtime にして TTL 経過を表現する
        os.utime(cache, (946684800, 946684800))

        body = (
            "国民の祝日・休日月日,国民の祝日・休日名称\n2024-02-11,建国記念の日\n".encode("cp932")
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

        source = CabinetOfficeCsvSource(cache_path=cache, ttl_seconds=60)
        holidays = list(source.load())
        assert called["count"] == 1, "キャッシュが古いとリクエストを呼ぶ"
        assert holidays[0].name == "建国記念の日"
        # キャッシュも更新されている
        assert cache.read_bytes() == body

    def test_falls_back_to_stale_cache_when_fetch_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """取得失敗時は古いキャッシュでも警告ログを出して動く。"""
        cache = tmp_path / "cache.csv"
        cache.write_bytes(
            "国民の祝日・休日月日,国民の祝日・休日名称\n2024-03-20,春分の日\n".encode("cp932")
        )
        import os

        os.utime(cache, (946684800, 946684800))  # 過去 mtime

        def _failing_get(*args, **kwargs):
            import requests  # type: ignore[import-not-found]

            raise requests.RequestException("network error")  # type: ignore[attr-defined]

        import sys
        import types

        requests_module = types.ModuleType("requests")
        requests_module.get = _failing_get  # type: ignore[attr-defined]
        requests_module.RequestException = type(  # type: ignore[attr-defined]
            "RequestException", (Exception,), {}
        )
        sys.modules["requests"] = requests_module
        monkeypatch.setattr("requests.get", _failing_get)

        source = CabinetOfficeCsvSource(cache_path=cache, ttl_seconds=60)
        with caplog.at_level(
            logging.WARNING,
            logger="comken.toolbox.holidays.sources.cabinet_office",
        ):
            holidays = list(source.load())
        assert holidays[0].name == "春分の日"
        assert any(
            "キャッシュで代用" in r.getMessage()
            for r in caplog.records
            if r.levelno == logging.WARNING
        )

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
        source = CabinetOfficeCsvSource(cache_path=cache, ttl_seconds=60)
        with pytest.raises(HolidayCalendarFetchError):
            list(source.load())


# ── ComkenMasterTableSource ───────────────────────────────────────────────


class TestComkenMasterTableSource:
    """社内管理表の「会社休日」シート読み取り。"""

    @staticmethod
    def _write_master(path: Path, rows: list[tuple[str, str]]) -> Path:
        from openpyxl import Workbook

        workbook = Workbook()
        worksheet = workbook.active
        assert worksheet is not None  # 新規 Workbook は必ず 1 枚持つ
        worksheet.title = "会社休日"
        worksheet.append(["日付", "名称"])
        for date_str, name in rows:
            worksheet.append([date_str, name])
        workbook.save(path)
        return path

    def test_loads_company_holidays(self, tmp_path: Path) -> None:
        """シートから ``Holiday`` のリストを返す。"""
        master = tmp_path / "master.xlsx"
        self._write_master(
            master,
            [("2024-12-30", "年末休暇"), ("2024-12-31", "年末休暇"), ("2024-09-01", "創立記念日")],
        )
        source = ComkenMasterTableSource(master)
        holidays = list(source.load())
        assert {h.name for h in holidays} == {"年末休暇", "創立記念日"}
        # 日付順にソートされている
        assert holidays[0].date == _dt.date(2024, 9, 1)

    def test_raises_when_sheet_missing(self, tmp_path: Path) -> None:
        """シートが無いシート名を指定すると ``HolidayCalendarSourceError``。"""
        from openpyxl import Workbook

        master = tmp_path / "master.xlsx"
        workbook = Workbook()
        worksheet = workbook.active
        assert worksheet is not None  # 新規 Workbook は必ず 1 枚持つ
        worksheet.title = "別のシート"
        workbook.save(master)
        source = ComkenMasterTableSource(master, sheet_name="会社休日")
        with pytest.raises(HolidayCalendarSourceError):
            list(source.load())

    def test_raises_when_file_missing(self, tmp_path: Path) -> None:
        """管理表ファイルが無いと ``HolidayCalendarSourceError``。"""
        source = ComkenMasterTableSource(tmp_path / "nope.xlsx")
        with pytest.raises(HolidayCalendarSourceError):
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
            (
                HolidayCalendarExpiredError(_dt.date(2024, 1, 1), _dt.date(2023, 1, 1)),
                "HolidayCalendarExpiredError",
            ),
        ],
    )
    def test_isinstance_of_base(
        self, exception: HolidayCalendarError, expected_name: str
    ) -> None:
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
            "comken.toolbox.holidays.calendar",
            "comken.toolbox.holidays.csv_source",
            "comken.toolbox.holidays.exceptions",
            "comken.toolbox.holidays.sources",
            "comken.toolbox.holidays.sources.cabinet_office",
            "comken.toolbox.holidays.sources.computed",
            "comken.toolbox.holidays.sources.master_table",
        ):
            sys.modules.pop(name, None)

        import comken.toolbox.holidays  # noqa: F401

        assert "requests" not in sys.modules, (
            "requests が import 時に読込まれています。"
            "CabinetOfficeCsvSource._download 内で遅延 import してください。"
        )


# ── ComputedHolidaySource ───────────────────────────────────────────────


class TestComputedHolidaySource:
    """``ComputedHolidaySource`` の出力（mokejp/holidays_jp のアルゴリズム）。"""

    def test_computed_returns_all_2026_holidays(self) -> None:
        """2026 年の祝日全部を個別に assert する。"""
        source = ComputedHolidaySource(from_year=2026, to_year=2026)
        holidays = {h.date: h.name for h in source.load()}
        expected = {
            # 1/1, 1/2, 1/3 は「年末年始休暇」（COMPANY_HOLIDAYS が
            # 元日を上書きする）年跨ぎの会社休日を 1 年単位で展開すると、
            # 12/29-1/3 が連続休業として ``year`` 年側に揃う。
            _dt.date(2026, 1, 1): "年末年始休暇",
            _dt.date(2026, 1, 2): "年末年始休暇",
            _dt.date(2026, 1, 3): "年末年始休暇",
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
            _dt.date(2026, 12, 29): "年末年始休暇",
            _dt.date(2026, 12, 30): "年末年始休暇",
            _dt.date(2026, 12, 31): "年末年始休暇",
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


# ── ComputedHolidaySource の会社休日 ──────────────────────────────────


class TestComputedCompanyHolidays:
    """``COMPANY_HOLIDAYS`` の 3 形式（単発 / 期間 / 特定年のみ）。"""

    @staticmethod
    def _with_company_holidays(
        monkeypatch: pytest.MonkeyPatch, entries: list[tuple]
    ) -> ComputedHolidaySource:
        """テスト用の ``COMPANY_HOLIDAYS`` を ``monkeypatch`` で差し込んで source を返す。

        ``TestNoImplicitRequests`` が ``sys.modules`` を再生成するため、
        このテストヘルパーでは毎回 ``computed`` モジュールを**今現在のインスタンス**で取り直す
        （古い参照が残っていると monkeypatch が反映されない）。
        """
        import importlib

        import comken.toolbox.holidays.sources.computed as computed_module

        # ``TestNoImplicitRequests`` が sys.modules を再構築している場合に備え、
        # 今ロード済みのモジュールを取得し直す
        computed_module = importlib.reload(computed_module)
        monkeypatch.setattr(computed_module, "COMPANY_HOLIDAYS", entries)
        # ``ComputedHolidaySource`` も同じモジュールのクラスなので再ロード後のクラスを返す
        return computed_module.ComputedHolidaySource(from_year=2026, to_year=2026)

    def test_computed_company_holidays_single(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """単発会社の休日 (int 月, int 日, name) が ``year`` 年で出てくる。"""
        source = self._with_company_holidays(monkeypatch, [(4, 1, "創立記念日")])
        holidays = {h.date: h.name for h in source.load()}
        assert holidays[_dt.date(2026, 4, 1)] == "創立記念日"

    def test_computed_company_holidays_range_year_crossing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """12/29 - 1/3 を年またぎで正しく展開（両端部分の両方を含む）。"""
        source = self._with_company_holidays(
            monkeypatch, [(12, 29, 1, 3, "年末年始休暇")]
        )
        holidays = {h.date: h.name for h in source.load()}
        # 12/29, 12/30, 12/31 と 1/1, 1/2, 1/3 が全部「年末年始休暇」になる
        for day in (29, 30, 31):
            assert holidays[_dt.date(2026, 12, day)] == "年末年始休暇"
        for day in (1, 2, 3):
            assert holidays[_dt.date(2026, 1, day)] == "年末年始休暇"

    def test_computed_company_holidays_range_same_year(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """同年内 (8/13 - 8/16) を展開する。"""
        source = self._with_company_holidays(monkeypatch, [(8, 13, 8, 16, "夏季休暇")])
        holidays = {h.date: h.name for h in source.load()}
        for day in (13, 14, 15, 16):
            assert holidays[_dt.date(2026, 8, day)] == "夏季休暇"

    def test_computed_company_holidays_specific_year(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """特定年のみ (_dt.date, _dt.date, name) 形式。"""
        entries = [(_dt.date(2026, 11, 4), _dt.date(2026, 11, 5), "臨時休業")]
        source = self._with_company_holidays(monkeypatch, entries)
        holidays = {h.date: h.name for h in source.load()}
        assert holidays[_dt.date(2026, 11, 4)] == "臨時休業"
        assert holidays[_dt.date(2026, 11, 5)] == "臨時休業"
        # 他の年には適用されない（2027 には出ない）。
        # monkeypatch は ``_with_company_holidays`` の中で既に同じ ``entries`` が
        # 設定されているので、2027 用の source を作っても 11/4 は出ないはず。
        source_2027 = ComputedHolidaySource(from_year=2027, to_year=2027)
        holidays_2027 = {h.date: h.name for h in source_2027.load()}
        assert holidays_2027.get(_dt.date(2027, 11, 4)) is None

    def test_computed_default_company_holidays_is_year_end_and_new_year(self) -> None:
        """既定の ``COMPANY_HOLIDAYS`` は年末年始休暇 (12/29 - 1/3) のみ。

        暫定デフォルトとして入れている。会社の正式な休日カレンダーが
        決まったら、ここを編集すればそのまま反映される。
        """
        from comken.toolbox.holidays.sources.computed import COMPANY_HOLIDAYS

        assert COMPANY_HOLIDAYS == [
            (12, 29, 1, 3, "年末年始休暇"),
        ]


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
        from comken.toolbox.holidays.sources.computed import (
            ComputedHolidaySource,
        )

        assert "requests" not in sys.modules, (
            "computed.py は requests を import すべきではない"
            "（純粋計算で動くソース）。"
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
        with caplog.at_level(logging.WARNING, logger="comken.toolbox.holidays.sources.computed"):
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


class TestCompanyHolidays:
    """``COMPANY_HOLIDAYS`` の展開を確認する。

    ``computed.py`` 冒頭のリストに休日を追加すると、そのまま ``Holiday`` に
    反映される。「会社都合で休みにしている日」がソースコードを開いた瞬間に
    分かる構造であることを保証する。
    """

    def test_year_end_and_new_year_holiday_default_present(self) -> None:
        """既定で 12/29 - 1/3 が「年末年始休暇」として休業扱いになる。

        12/29, 12/30, 12/31, 1/1, 1/2, 1/3 の 6 日間が ``Holiday`` に
        入ることを確認する。年跨ぎ（12→1）が正しく展開されるかも兼ねる。
        """
        holidays = ComputedHolidaySource().load()
        assert Holiday(date=_dt.date(2026, 12, 29), name="年末年始休暇") in holidays
        assert Holiday(date=_dt.date(2026, 12, 30), name="年末年始休暇") in holidays
        assert Holiday(date=_dt.date(2026, 12, 31), name="年末年始休暇") in holidays
        assert Holiday(date=_dt.date(2027, 1, 1), name="年末年始休暇") in holidays
        assert Holiday(date=_dt.date(2027, 1, 2), name="年末年始休暇") in holidays
        assert Holiday(date=_dt.date(2027, 1, 3), name="年末年始休暇") in holidays

