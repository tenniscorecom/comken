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
from comken.exceptions import ScheduleWeekdayInvalidError
from comken.services.salesforce_downloader.sheets.schedule import (
    FREQUENCY_BUSINESS_DAY,
    FREQUENCY_DAILY,
    HOLIDAY_AFTER,
    HOLIDAY_BEFORE,
    HOLIDAY_FETCH,
    HOLIDAY_SKIP,
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
        "start_time": dt.time(9, 0),
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
            start_time=None,
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


class TestIsDueTimeOptional:
    """「毎日」「毎週」「毎月」で ``取得開始時刻`` を空欄にすると、時刻条件なしで due 判定する。"""

    @pytest.mark.parametrize("frequency", ["毎日", "毎週", "毎月"])
    def test_blank_start_time_means_due_at_any_time(self, frequency):
        """``start_time is None`` は「時刻条件なし」と解釈する。

        同じレポートを1日のうちいつ取っても中身が変わらない（例: 前日以前の確定済み
        データ）の用途を想定。「1時間ごと」では空欄を許さないので、この挙動は適用しない。
        """
        rule = _rule(frequency=frequency, start_time=None)
        # 0:00 と 23:59 の両方で True を返す（=任意の時刻で due）
        assert rule.is_due(dt.datetime(2026, 1, 1, 0, 0)) is True  # noqa: DTZ001
        assert rule.is_due(dt.datetime(2026, 1, 1, 23, 59)) is True  # noqa: DTZ001

    def test_blank_start_time_still_respects_date_match(self):
        """``start_time`` が空欄でも、曜日や月の日など日付条件は引き続き適用される。"""
        # 「毎週・水曜」の行で、月曜に問い合わせると日付不一致で False
        rule = _rule(frequency="毎週", raw_weekday="水", start_time=None)
        # 2026/1/5 は月曜
        monday = dt.datetime(2026, 1, 5, 12, 0)  # noqa: DTZ001
        assert rule.is_due(monday) is False
        # 2026/1/7 は水曜
        wednesday = dt.datetime(2026, 1, 7, 12, 0)  # noqa: DTZ001
        assert rule.is_due(wednesday) is True


class TestBusinessDayFrequency:
    """「毎営業日」(`FREQUENCY_BUSINESS_DAY`) の挙動を ``is_due()`` で確かめる。

    「毎営業日」は曜日フィルタ（土日を除く）のみで、祝日の除外は
    ``holiday_policy`` の組み合わせで実現する（``HOLIDAY_SKIP`` を既定で
    組み合わせれば、土日祝日を除く真の営業日だけになる）。
    """

    @pytest.mark.parametrize(
        "date, expected",
        [
            # 2026/1/5(月) → True, 1/6(火) → True, ..., 1/9(金) → True
            (dt.date(2026, 1, 5), True),  # 月
            (dt.date(2026, 1, 6), True),  # 火
            (dt.date(2026, 1, 7), True),  # 水
            (dt.date(2026, 1, 8), True),  # 木
            (dt.date(2026, 1, 9), True),  # 金
            # 2026/1/10(土) → False, 1/11(日) → False
            (dt.date(2026, 1, 10), False),  # 土
            (dt.date(2026, 1, 11), False),  # 日
        ],
    )
    def test_skips_weekends_and_runs_on_weekdays(self, date, expected):
        """「毎営業日」行は土曜・日曜で False、平日で True。"""
        rule = _rule(
            frequency=FREQUENCY_BUSINESS_DAY,
            raw_weekday="",
            raw_day_of_month="",
            start_time=None,  # 時刻条件を邪魔しないため None
        )
        when = dt.datetime.combine(date, dt.time(12, 0))
        assert rule.is_due(when) is expected

    def test_respects_start_time_on_business_day(self):
        """「毎営業日」行は ``start_time`` も従来どおり適用する（既存挙動と共通）。"""
        rule = _rule(
            frequency=FREQUENCY_BUSINESS_DAY,
            raw_weekday="",
            raw_day_of_month="",
            start_time=dt.time(9, 0),
        )
        # 2026/1/5(月) 8:00 → start_time 前なので False
        early = dt.datetime(2026, 1, 5, 8, 0)  # noqa: DTZ001
        assert rule.is_due(early) is False
        # 2026/1/5(月) 9:00 → True
        on_time = dt.datetime(2026, 1, 5, 9, 0)  # noqa: DTZ001
        assert rule.is_due(on_time) is True
        # 2026/1/10(土) 9:00 → 曜日フィルタで False（土曜）
        saturday = dt.datetime(2026, 1, 10, 9, 0)  # noqa: DTZ001
        assert rule.is_due(saturday) is False

    def test_holiday_skip_combined_with_business_day_excludes_holidays(self):
        """「毎営業日」+「取得しない」で土日祝日を除く真の営業日だけになる。

        2026/1/5(月) が祝日 ``holidays`` 引数に含まれていれば、曜日フィルタは
        パスしても ``HOLIDAY_SKIP`` で False に落ちる。
        """
        rule = _rule(
            frequency=FREQUENCY_BUSINESS_DAY,
            raw_weekday="",
            raw_day_of_month="",
            start_time=None,
            holiday_policy=HOLIDAY_SKIP,
        )
        # 祝日の月曜 → 曜日フィルタは通るが HOLIDAY_SKIP で False
        holiday_monday = dt.datetime(2026, 1, 5, 12, 0)  # noqa: DTZ001
        assert rule.is_due(holiday_monday, holidays={dt.date(2026, 1, 5)}) is False
        # 同じ月曜を holidays=空で問い合わせれば True
        assert rule.is_due(holiday_monday, holidays=set()) is True


class TestDailyFrequencyRegression:
    """「毎日」(`FREQUENCY_DAILY`) が土日でも True のまま（既存挙動）を回帰確認する。

    「毎営業日」を新設した影響が「毎日」に漏れていないことを保証するための、
    1 回限りのスモークテスト。
    """

    @pytest.mark.parametrize(
        "date",
        [
            dt.date(2026, 1, 10),  # 土
            dt.date(2026, 1, 11),  # 日
            dt.date(2026, 1, 12),  # 月
        ],
    )
    def test_daily_returns_true_on_weekends(self, date):
        """「毎日」は土日でも平日でも True。"""
        rule = _rule(
            frequency=FREQUENCY_DAILY,
            raw_weekday="",
            raw_day_of_month="",
            start_time=None,
        )
        when = dt.datetime.combine(date, dt.time(12, 0))
        assert rule.is_due(when) is True


class TestHolidayPolicySkipFetch:
    """``HOLIDAY_SKIP`` / ``HOLIDAY_FETCH`` の既存挙動が変わっていないこと（回帰確認）。

    「1営業日前」「1営業日後」は ``TestHolidayPolicyShifted`` で別クラスにまとめる。
    祝日判定に使う ``holidays`` 引数（=呼び出し元 ``download_scheduled`` が当日分
    だけ渡す ``set[date]``）もそのまま動くことを確認する。
    """

    def test_skip_does_not_match_on_holiday(self):
        """「取得しない」行で、対象日が祝日（holidays 引数に含まれる）なら ``False``。"""
        rule = _rule(frequency="毎週", raw_weekday="月", holiday_policy=HOLIDAY_SKIP)
        # 2026/1/5 は月曜
        when = dt.datetime(2026, 1, 5, 12, 0)  # noqa: DTZ001
        # holidays 引数に対象日が入っていない → 取得
        assert rule.is_due(when, holidays=set()) is True
        # holidays 引数に対象日が入っている → スキップ
        assert rule.is_due(when, holidays={dt.date(2026, 1, 5)}) is False

    def test_fetch_matches_even_on_holiday(self):
        """「取得する」行は祝日でもそのまま取得する。"""
        rule = _rule(frequency="毎週", raw_weekday="月", holiday_policy=HOLIDAY_FETCH)
        when = dt.datetime(2026, 1, 5, 12, 0)  # noqa: DTZ001
        # holidays 引数の中身に関わらず True（曜日が月曜なら必ず True）
        assert rule.is_due(when, holidays=set()) is True
        assert rule.is_due(when, holidays={dt.date(2026, 1, 5)}) is True

    def test_skip_does_not_match_on_non_weekday_even_when_not_holiday(self):
        """曜日条件を満たさない日は祝日でなくても False（既存挙動）。"""
        rule = _rule(frequency="毎週", raw_weekday="月", holiday_policy=HOLIDAY_SKIP)
        # 2026/1/7 は水曜
        when = dt.datetime(2026, 1, 7, 12, 0)  # noqa: DTZ001
        assert rule.is_due(when, holidays=set()) is False


class TestHolidayPolicyShifted:
    """「1営業日前」「1営業日後」の探索ロジック。

    単発の祝日、複数連続の祝日、対象日が土日と重なるケース、
    既存挙動（HOLIDAY_SKIP/FETCH）が破壊されていないことを確かめる。
    祝日判定は ``calendar`` 経由（``is_holiday``）なので、``holidays`` 引数には
    頼らない。テストでは ``_make_fake_calendar`` のフェイクを使い、対象日が
    祝日のケースも非祝日のケースも自由に作れる。
    """

    def _weekly_rule(self, weekday_name: str, holiday_policy: str) -> ScheduleRule:
        return _rule(
            frequency="毎週",
            raw_weekday=weekday_name,
            holiday_policy=holiday_policy,
            start_time=None,  # 時刻判定を邪魔しないため None
        )

    def test_shifted_before_single_monday_holiday(self):
        """「1営業日前」: 月曜が祝日 → 前の金曜が True、月曜自身は False。

        2026/1/2（金）→ 2026/1/5（月=祝日）→ 2026/1/6（火 = 月曜の翌営業日）
        ``date=2026/1/2`` で問い合わせると、``date+1`` から次の営業日に達するまで
        の間に祝日である月曜（2026/1/5）が含まれるので True。
        """
        calendar = _make_fake_calendar({dt.date(2026, 1, 5)})  # 1/5(月)だけ祝日
        rule = self._weekly_rule("月", HOLIDAY_BEFORE)

        # 前営業日（金曜）→ True
        assert (
            rule.is_due(dt.datetime(2026, 1, 2, 12, 0), calendar=calendar) is True  # noqa: DTZ001
        )
        # 祝日である月曜 → 対象日自体は False
        assert (
            rule.is_due(dt.datetime(2026, 1, 5, 12, 0), calendar=calendar) is False  # noqa: DTZ001
        )
        # 翌営業日（火曜）→ False（月曜の翌営業日であり、1営業日前側の終端を超える）
        assert (
            rule.is_due(dt.datetime(2026, 1, 6, 12, 0), calendar=calendar) is False  # noqa: DTZ001
        )

    def test_shifted_after_single_monday_holiday(self):
        """「1営業日後」: 月曜が祝日 → 翌火曜が True、月曜自身は False。

        ``date=2026/1/6`` で問い合わせると、``date-1`` から前の営業日に達するまで
        の間に祝日である月曜（2026/1/5）が含まれるので True。
        """
        calendar = _make_fake_calendar({dt.date(2026, 1, 5)})  # 1/5(月)だけ祝日
        rule = self._weekly_rule("月", HOLIDAY_AFTER)

        # 翌営業日（火曜）→ True
        assert (
            rule.is_due(dt.datetime(2026, 1, 6, 12, 0), calendar=calendar) is True  # noqa: DTZ001
        )
        # 祝日である月曜 → 対象日自体は False
        assert (
            rule.is_due(dt.datetime(2026, 1, 5, 12, 0), calendar=calendar) is False  # noqa: DTZ001
        )
        # 前営業日（金曜）→ False（翌営業日側の終端を超える）
        assert (
            rule.is_due(dt.datetime(2026, 1, 2, 12, 0), calendar=calendar) is False  # noqa: DTZ001
        )

    def test_shifted_before_consecutive_monday_tuesday_holidays(self):
        """「1営業日前」: 月・火が祝日 → 前の金曜が True、火曜は False。

        2 連続祝日のときは「金曜（→月曜=祝日の 1 営業日前）」だけが True になり、
        途中の火曜（祝日）が True になってはならない。
        """
        calendar = _make_fake_calendar(
            {dt.date(2026, 1, 5), dt.date(2026, 1, 6)}  # 月・火が祝日
        )
        rule = self._weekly_rule("月", HOLIDAY_BEFORE)

        # 前金曜 → True（月曜が祝日で、1営業日前が金曜）
        assert (
            rule.is_due(dt.datetime(2026, 1, 2, 12, 0), calendar=calendar) is True  # noqa: DTZ001
        )
        # 月曜（祝日）→ False
        assert (
            rule.is_due(dt.datetime(2026, 1, 5, 12, 0), calendar=calendar) is False  # noqa: DTZ001
        )
        # 火曜（祝日だが、weekday=月 条件を満たさない）→ False（条件不一致）
        assert (
            rule.is_due(dt.datetime(2026, 1, 6, 12, 0), calendar=calendar) is False  # noqa: DTZ001
        )
        # 水曜（翌営業日、探索終端を超える）→ False
        assert (
            rule.is_due(dt.datetime(2026, 1, 7, 12, 0), calendar=calendar) is False  # noqa: DTZ001
        )

    def test_shifted_after_only_one_of_consecutive_holidays_triggers(self):
        """「1営業日後」: 月・火が祝日で対象日が月曜 → 水曜が True、火曜が False。

        連続祝日のときも「翌営業日（水曜）」だけが True になる。途中の火曜は
        祝日だが、「対象日条件（weekday=月）」を満たさないので探索中に True 判定
        が挟まらない。
        """
        calendar = _make_fake_calendar(
            {dt.date(2026, 1, 5), dt.date(2026, 1, 6)}  # 月・火が祝日
        )
        rule = self._weekly_rule("月", HOLIDAY_AFTER)

        # 水曜 → True（月曜の翌営業日 = 1営業日後）
        assert (
            rule.is_due(dt.datetime(2026, 1, 7, 12, 0), calendar=calendar) is True  # noqa: DTZ001
        )
        # 月曜（祝日）→ False
        assert (
            rule.is_due(dt.datetime(2026, 1, 5, 12, 0), calendar=calendar) is False  # noqa: DTZ001
        )
        # 火曜（祝日、ただし weekday=月 条件を満たさない）→ False
        assert (
            rule.is_due(dt.datetime(2026, 1, 6, 12, 0), calendar=calendar) is False  # noqa: DTZ001
        )

    def test_shifted_before_target_date_itself_is_never_true(self):
        """「1営業日前」: 対象日が祝日でも非祝日でも、対象日自体は常に False。

        既存テスト（``TestHolidayPolicySkipFetch``）と組み合わせた回帰確認。
        """
        calendar = _make_fake_calendar({dt.date(2026, 1, 5)})  # 1/5(月)だけ祝日
        rule = self._weekly_rule("月", HOLIDAY_BEFORE)

        # 祝日月曜 → 対象日自体は False
        assert (
            rule.is_due(dt.datetime(2026, 1, 5, 12, 0), calendar=calendar) is False  # noqa: DTZ001
        )
        # 翌週の月曜（非祝日）→ 対象日自体は False（前営業日側でも翌営業日側でもない）
        assert (
            rule.is_due(dt.datetime(2026, 1, 12, 12, 0), calendar=calendar) is False  # noqa: DTZ001
        )

    def test_shifted_non_business_day_target_is_false(self):
        """「1営業日前/後」: ``date`` 自身が非営業日（土日）なら False。

        ずらし先になり得ないため、土日に問い合わせたら False。
        """
        calendar = _make_fake_calendar({dt.date(2026, 1, 5)})  # 1/5(月)だけ祝日
        rule = self._weekly_rule("月", HOLIDAY_BEFORE)

        # 2026/1/3 は土曜。ずらし先になり得ない
        assert (
            rule.is_due(dt.datetime(2026, 1, 3, 12, 0), calendar=calendar) is False  # noqa: DTZ001
        )
        # 2026/1/4 は日曜
        assert (
            rule.is_due(dt.datetime(2026, 1, 4, 12, 0), calendar=calendar) is False  # noqa: DTZ001
        )

    def test_shifted_before_does_not_trigger_when_no_holiday_target_between(self):
        """「1営業日前」: 間に祝日対象日がなければ False（翌営業日に直接ぶつかる）。"""
        calendar = _make_fake_calendar(set())  # 祝日は無い
        rule = self._weekly_rule("月", HOLIDAY_BEFORE)

        # 月曜は祝日ではないが、対象日（翌営業日）との間に祝日対象日が無い
        # 2026/1/5(月) → 2026/1/6(火、=翌営業日) でぶつかる → False
        # ただし月曜自体は「対象日条件を満たす」+「祝日ではない」となるため
        # ``_raw_date_matches`` が True になり HOLIDAY_BEFORE のときは対象日 False → ルートの
        # 「ずらし先探索」には来ない。翌営業日 2026/1/6 を問い合わせた場合のみが
        # 「HOLIDAY_BEFORE 探索」の対象となり、その間には祝日が無いので False
        assert (
            rule.is_due(dt.datetime(2026, 1, 6, 12, 0), calendar=calendar) is False  # noqa: DTZ001
        )

    def test_shifted_before_with_three_consecutive_holidays(self):
        """「1営業日前」: 月・火・水と3日連続の祝日 → 探索区間に複数の祝日があっても True。

        対象日（月曜）の翌日から次の営業日に達するまでの非営業日区間に「祝日かつ
        対象日条件を満たす日」が1つでも含まれていれば True。複数含まれていても
        結果は同じ（最初に発見した時点で True を返す）。
        """
        calendar = _make_fake_calendar(
            {
                dt.date(2026, 1, 5),  # 月
                dt.date(2026, 1, 6),  # 火
                dt.date(2026, 1, 7),  # 水
            }
        )
        rule = self._weekly_rule("月", HOLIDAY_BEFORE)

        # 前金曜 → True
        assert (
            rule.is_due(dt.datetime(2026, 1, 2, 12, 0), calendar=calendar) is True  # noqa: DTZ001
        )
        # 月曜 → False（対象日自体）
        assert (
            rule.is_due(dt.datetime(2026, 1, 5, 12, 0), calendar=calendar) is False  # noqa: DTZ001
        )
        # 木曜（翌営業日、探索区間の終端）→ False
        assert (
            rule.is_due(dt.datetime(2026, 1, 8, 12, 0), calendar=calendar) is False  # noqa: DTZ001
        )

    def test_shifted_uses_calendar_not_holidays_argument(self):
        """「1営業日前/後」の探索は ``holidays`` 引数ではなく ``calendar`` を使う。

        ``holidays=set()``（空）を明示的に渡しても、未来/過去の祝日を
        ``calendar.is_holiday()`` 経由で正しく拾うこと。これが「両方を
        辻褄が合う形で使う」要件の核。
        """
        calendar = _make_fake_calendar({dt.date(2026, 1, 5)})  # 1/5(月)だけ祝日
        rule = self._weekly_rule("月", HOLIDAY_BEFORE)

        # holidays は空だが、calendar 経由で 1/5 が祝日と判定されて True
        assert (
            rule.is_due(dt.datetime(2026, 1, 2, 12, 0), holidays=set(), calendar=calendar) is True  # noqa: DTZ001
        )


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
