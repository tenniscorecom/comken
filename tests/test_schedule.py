"""``ScheduleRule`` の ``raw_weekday`` / ``raw_day_of_month`` のパースと判定ロジックを検証する。

``raw_*`` フィールドは宣言だけでパースは行わず、``@property`` で派生値（``weekday`` /
``day_of_month`` / ``month_end`` / ``nth_business_day``）を取り出す。型変換は
``report_master.py`` の ``_to_bool`` / ``_to_time`` を ``MasterRow`` 経由で共用
しているため、``is_due()`` 側の挙動を主にここで確かめる。
"""

import datetime as dt
from typing import Any, cast

import pytest

from comken.core.holidays import HolidayCalendar, nth_business_day_of_month
from comken.exceptions import ScheduleIntervalMissingError, ScheduleWeekdayInvalidError
from comken.services.salesforce_downloader.sheets.schedule import (
    FREQUENCY_HOURLY,
    ScheduleRule,
)


def _rule(**overrides: Any) -> ScheduleRule:
    """ベースになる ``ScheduleRule`` を返す。``overrides`` でフィールドを差し替える。

    ``__init__`` のシグネチャは ``@dataclass(kw_only=True)`` のため、``column()``
    宣言のあるフィールドだけを ``**overrides`` で渡せば、残りは ``field`` の
    既定値（``str`` の ``""`` / ``bool`` の ``True`` / ``None`` / ``HOLIDAY_SKIP``）
    が埋まる。
    """
    defaults: dict[str, Any] = {
        "schedule_key": "S1",
        "report_key": "1001",
        "frequency": "毎日",
        "run_time": dt.time(9, 0),
        "raw_weekday": "",
        "raw_day_of_month": "",
        "holiday_policy": "取得しない",
        "enabled": True,
    }
    defaults.update(overrides)
    return ScheduleRule(**defaults)


class TestWeekdayProperty:
    """``raw_weekday`` から ``weekday`` プロパティへの変換。"""

    def test_returns_int_for_japanese_name(self):
        rule = _rule(frequency="毎週", raw_weekday="水")
        assert rule.weekday == 2

    def test_blank_returns_none(self):
        rule = _rule()
        assert rule.weekday is None

    def test_accepts_with_weekday_suffix(self):
        rule = _rule(raw_weekday="月曜日")
        assert rule.weekday == 0

    def test_invalid_raises(self):
        rule = _rule(raw_weekday="不明")
        with pytest.raises(ScheduleWeekdayInvalidError):
            _ = rule.weekday


class TestDayOfMonthProperty:
    """``raw_day_of_month`` から ``day_of_month`` / ``month_end`` / ``nth_business_day`` への変換。

    3 つのプロパティを1クラスでまとめて検証する（パース入口が共通なので、テストも
    一箇所に集約する方が読みやすい）。
    """

    def test_number(self):
        rule = _rule(frequency="毎月", raw_day_of_month="15")
        assert rule.day_of_month == 15
        assert rule.month_end is False
        assert rule.nth_business_day is None

    def test_month_end_word(self):
        rule = _rule(raw_day_of_month="月末")
        assert rule.month_end is True
        assert rule.day_of_month is None
        assert rule.nth_business_day is None

    def test_nth_business_day(self):
        rule = _rule(raw_day_of_month="第2営業日")
        assert rule.nth_business_day == 2
        assert rule.day_of_month is None
        assert rule.month_end is False

    def test_nth_business_day_above_ten(self):
        """N が 10 以上の桁でも拾える。"""
        rule = _rule(raw_day_of_month="第15営業日")
        assert rule.nth_business_day == 15
        assert rule.day_of_month is None
        assert rule.month_end is False

    def test_blank_returns_no_specification(self):
        rule = _rule()
        assert rule.day_of_month is None
        assert rule.month_end is False
        assert rule.nth_business_day is None

    @pytest.mark.parametrize("text", ["第二営業日", "2営業日", "第2", "来月"])
    def test_invalid_format_raises_value_error(self, text):
        """正規表現にも数字にも合わない表記は ``ValueError``（=``int()`` 由来）。

        「第二営業日」は漢数字なので正規表現不一致 → ``int()`` で失敗。
        「2営業日」は「第」接頭辞が無いので正規表現不一致。
        「第2」は「営業日」サフィックスが無いので正規表現不一致。
        「来月」は数字でも正規表現でもないので ``int()`` で失敗。
        """
        rule = _rule(raw_day_of_month=text)
        with pytest.raises(ValueError):
            _ = rule.day_of_month


class TestNthBusinessDayIsDue:
    """``is_due()`` の「第N営業日」分岐を偽カレンダー経由で確認する。"""

    @staticmethod
    def _monthly_rule(date_marker: str) -> ScheduleRule:
        return _rule(
            frequency="毎月",
            raw_weekday="",
            run_time=None,
            raw_day_of_month=date_marker,
        )

    def test_matches_on_calculated_nth_business_day(self):
        """「第2営業日」の設定で、フェイクカレンダーの「第2営業日」日付にだけ ``True``。"""
        holidays_set = {dt.date(2026, 1, 1)}  # 1/1（木）だけ祝日扱い
        calendar = _make_fake_calendar(holidays_set)

        # 期待値は実際の ``nth_business_day_of_month`` で計算する（手計算しない）
        second_business_day = nth_business_day_of_month(dt.date(2026, 1, 1), 2, calendar=calendar)

        rule = self._monthly_rule("第2営業日")
        # 計算上の「第2営業日」は True
        on_target = dt.datetime.combine(second_business_day, dt.time(12, 0))
        assert rule.is_due(on_target, calendar=calendar) is True
        # 前日は False
        day_before = dt.datetime.combine(second_business_day - dt.timedelta(days=1), dt.time(12, 0))
        assert rule.is_due(day_before, calendar=calendar) is False
        # 翌日も False
        day_after = dt.datetime.combine(second_business_day + dt.timedelta(days=1), dt.time(12, 0))
        assert rule.is_due(day_after, calendar=calendar) is False

    def test_exceeding_business_days_returns_false_silently(self):
        """「第35営業日」のような月の営業日数を超える指定で ``False`` を返す。

        ``BusinessDayNotFoundError`` を上位へ伝播させず、この日を「対象外」として
        扱う（``service.py`` の「1件失敗でも他は続ける」設計を守るため）。
        """
        calendar = _make_fake_calendar(set())  # 祝日は 1 件も無い想定
        rule = self._monthly_rule("第35営業日")
        # 1月のどこを問い合わせても ``False``（例外が飛ばない）
        for day in range(1, 32):
            when = dt.datetime(2026, 1, day, 12, 0)  # noqa: DTZ001
            assert rule.is_due(when, calendar=calendar) is False

    def test_uses_default_calendar_when_calendar_omitted(self):
        """``calendar`` 引数を渡さなくても ``is_due`` 内で ``default_calendar`` に
        フォールバックして動くこと（``service.py`` 側の呼び出しが ``calendar`` を
        明示しない前提を守るため）。
        """
        rule = self._monthly_rule("第2営業日")
        # 正月休みの影響を受けたくないので 2 月を使う。
        # 計算上の第 2 営業日を ``default_calendar()`` 経由で取得して、
        # その日だけ ``is_due`` が True になることを確認
        expected_second = nth_business_day_of_month(dt.date(2026, 2, 1), 2)
        on_target = dt.datetime.combine(expected_second, dt.time(12, 0))
        assert rule.is_due(on_target) is True


class TestIsHourlyDue:
    """``_is_hourly_due`` の60分固定の挙動。"""

    def _hourly_rule(self, **overrides: object) -> ScheduleRule:
        return _rule(frequency=FREQUENCY_HOURLY, run_time=dt.time(9, 0), **overrides)

    def test_is_due_at_start_time(self):
        """開始時刻ちょうどは ``is_due()`` で True。"""
        rule = self._hourly_rule()
        now = dt.datetime(2026, 1, 1, 9, 0)  # noqa: DTZ001
        assert rule.is_due(now) is True

    def test_is_due_at_each_60_minute_multiple(self):
        """開始時刻から 60 分刻みの時刻に ``True``。"""
        rule = self._hourly_rule()
        for hour in [9, 10, 11, 12, 23]:
            now = dt.datetime(2026, 1, 1, hour, 0)  # noqa: DTZ001
            assert rule.is_due(now) is True, f"{hour}:00 should be due"

    def test_is_not_due_at_non_multiple(self):
        """60分の倍数でない時刻は ``False``（間隔列は廃止したので 30 分刻みは対象外）。"""
        rule = self._hourly_rule()
        now = dt.datetime(2026, 1, 1, 9, 30)  # noqa: DTZ001
        assert rule.is_due(now) is False

    def test_is_not_due_before_start_time(self):
        """開始時刻より前は ``False``。"""
        rule = self._hourly_rule()
        now = dt.datetime(2026, 1, 1, 8, 30)  # noqa: DTZ001
        assert rule.is_due(now) is False

    def test_missing_run_time_raises(self):
        """``run_time`` が無い「1時間ごと」行は ``ScheduleIntervalMissingError``。"""
        rule = _rule(frequency=FREQUENCY_HOURLY, run_time=None)
        now = dt.datetime(2026, 1, 1, 9, 0)  # noqa: DTZ001
        with pytest.raises(ScheduleIntervalMissingError):
            rule.is_due(now)


class TestIsDueTimeOptional:
    """「毎日」「毎週」「毎月」で ``取得時刻`` を空欄にすると、時刻条件なしで due 判定する。"""

    @pytest.mark.parametrize("frequency", ["毎日", "毎週", "毎月"])
    def test_blank_run_time_means_due_at_any_time(self, frequency):
        """``run_time is None`` は「時刻条件なし」と解釈する。

        同じレポートを1日のうちいつ取っても中身が変わらない（例: 前日以前の確定済み
        データ）の用途を想定。「1時間ごと」では空欄を許さないので、この挙動は適用しない。
        """
        rule = _rule(frequency=frequency, run_time=None)
        # 0:00 と 23:59 の両方で True を返す（=任意の時刻で due）
        assert rule.is_due(dt.datetime(2026, 1, 1, 0, 0)) is True  # noqa: DTZ001
        assert rule.is_due(dt.datetime(2026, 1, 1, 23, 59)) is True  # noqa: DTZ001

    def test_blank_run_time_still_respects_date_match(self):
        """``run_time`` が空欄でも、曜日や月の日など日付条件は引き続き適用される。"""
        # 「毎週・水曜」の行で、月曜に問い合わせると日付不一致で False
        rule = _rule(frequency="毎週", raw_weekday="水", run_time=None)
        # 2026/1/5 は月曜
        monday = dt.datetime(2026, 1, 5, 12, 0)  # noqa: DTZ001
        assert rule.is_due(monday) is False
        # 2026/1/7 は水曜
        wednesday = dt.datetime(2026, 1, 7, 12, 0)  # noqa: DTZ001
        assert rule.is_due(wednesday) is True


def _make_fake_calendar(holidays_set: set[dt.date]) -> HolidayCalendar:
    """``comken.core.holidays.HolidayCalendar`` の最小フェイクを返す。

    ``tests/test_service.py`` の ``_FakeCalendar`` と同じく ``is_holiday`` だけを
    実装する発想だが、``nth_business_day_of_month`` 経由で ``is_business_day`` が
    呼ばれたときに内部で ``_maybe_warn_expiring`` も叩かれるため、それも no-op で
    用意しておく。戻り値は ``HolidayCalendar`` と ``cast`` して流し込み、
    内部実装の差はテスト都合で隠す。
    """

    class _FakeCalendar:
        def is_holiday(self, target: dt.date) -> bool:
            return target in holidays_set

        def _maybe_warn_expiring(self, _: dt.date) -> None:
            return None

    return cast(HolidayCalendar, _FakeCalendar())
