"""ScheduleRule.from_row() の行パースを検証する。

型変換は report_master.py の _to_bool / _to_time を共用しているため、
「はい」等の表記や datetime セルの受け取りもここで確かめる。
"""

import datetime as dt
from typing import cast

import pytest

from comken.core.holidays import HolidayCalendar, nth_business_day_of_month
from comken.exceptions import (
    ScheduleIntervalMissingError,
    ScheduleRequiredValueMissingError,
    ScheduleWeekdayInvalidError,
)
from comken.services.salesforce_downloader.schedule import FREQUENCY_HOURLY, ScheduleRule


def base_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "スケジュールキー": "S1",
        "レポートキー": "1001",
        "取得頻度": "毎日",
        "取得時刻": "09:00",
        "有効": "○",
    }
    row.update(overrides)
    return row


class TestFromRow:
    """必須項目と型変換。"""

    def test_required_fields_missing_raises(self):
        row = base_row()
        del row["レポートキー"]
        with pytest.raises(ScheduleRequiredValueMissingError):
            ScheduleRule.from_row(row)

    @pytest.mark.parametrize("text", ["○", "有効", "はい", "true", "True", "TRUE"])
    def test_enabled_accepts_common_true_words(self, text):
        rule = ScheduleRule.from_row(base_row(有効=text))
        assert rule.enabled is True

    def test_enabled_defaults_to_false_when_blank(self):
        rule = ScheduleRule.from_row(base_row(有効=""))
        assert rule.enabled is False

    def test_run_time_accepts_isoformat_string(self):
        rule = ScheduleRule.from_row(base_row(取得時刻="09:30"))
        assert rule.run_time == dt.time(9, 30)

    def test_run_time_accepts_datetime_cell(self):
        # Excel の時刻セルは datetime で返ることがある
        rule = ScheduleRule.from_row(base_row(取得時刻=dt.datetime(2026, 1, 1, 9, 30, 45)))  # noqa: DTZ001
        assert rule.run_time == dt.time(9, 30)

    def test_weekday_parses_japanese_name(self):
        rule = ScheduleRule.from_row(base_row(取得頻度="毎週", 曜日="水"))
        assert rule.weekday == 2

    def test_weekday_invalid_raises(self):
        with pytest.raises(ScheduleWeekdayInvalidError):
            ScheduleRule.from_row(base_row(取得頻度="毎週", 曜日="不明"))

    def test_day_of_month_parses_number(self):
        """「日付」列に 1〜31 の数字を書いたとき、``day_of_month`` が int になる。"""
        rule = ScheduleRule.from_row(base_row(取得頻度="毎月", 日付="15"))
        assert rule.day_of_month == 15
        assert rule.month_end is False

    def test_day_of_month_accepts_month_end_word(self):
        """「日付」列に「月末」と書いたとき、``month_end`` が True になる。"""
        rule = ScheduleRule.from_row(base_row(取得頻度="毎月", 日付="月末"))
        assert rule.month_end is True
        assert rule.day_of_month is None

    def test_day_of_month_blank_means_no_specification(self):
        """「日付」列が空欄のときは ``day_of_month=None``, ``month_end=False``。"""
        rule = ScheduleRule.from_row(base_row(取得頻度="毎月", 日付=""))
        assert rule.day_of_month is None
        assert rule.month_end is False


class TestIsHourlyDue:
    """``_is_hourly_due`` の終了時刻撤廃後の挙動を直接検証する。"""

    def _hourly_rule(self, **overrides: object) -> ScheduleRule:
        row = base_row(
            **{
                "取得頻度": FREQUENCY_HOURLY,
                "取得時刻": "09:00",
                "取得間隔（分）": 60,
                "曜日": "",
                "日付": "",
            }
        )
        row.update(overrides)
        return ScheduleRule.from_row(row)

    def test_is_due_at_start_time(self):
        """開始時刻ちょうどは ``is_due()`` で True。"""
        rule = self._hourly_rule()
        now = dt.datetime(2026, 1, 1, 9, 0)  # noqa: DTZ001
        assert rule.is_due(now) is True

    def test_is_due_after_multiple_intervals(self):
        """開始時刻から ``interval_minutes`` の倍数だけ経過した時刻でも True。"""
        rule = self._hourly_rule(**{"取得間隔（分）": 30})
        # 09:00 開始で 10:30 = 90 分後 (= 30 分の倍数)
        now = dt.datetime(2026, 1, 1, 10, 30)  # noqa: DTZ001
        assert rule.is_due(now) is True

    def test_no_end_time_means_due_late_in_the_day(self):
        """終了時刻という概念が無いので、開始時刻からかなり後でも間隔条件を満たせば True。

        旧仕様なら ``取得終了時刻`` を過ぎて ``False`` になっていたケース。
        """
        rule = self._hourly_rule()
        # 開始 09:00 から 14 時間後（= 23:00）でも 60 分間隔なら True
        now = dt.datetime(2026, 1, 1, 23, 0)  # noqa: DTZ001
        assert rule.is_due(now) is True

    def test_missing_run_time_raises(self):
        """``run_time`` も ``interval_minutes`` も無い行は ``ScheduleIntervalMissingError``。"""
        rule = ScheduleRule.from_row(
            base_row(
                **{
                    "取得頻度": FREQUENCY_HOURLY,
                    "取得時刻": "",
                    "取得間隔（分）": "",
                }
            )
        )
        now = dt.datetime(2026, 1, 1, 9, 0)  # noqa: DTZ001
        with pytest.raises(ScheduleIntervalMissingError):
            rule.is_due(now)


class TestIsDueTimeOptional:
    """「毎日」「毎週」「毎月」で ``取得時刻`` を空欄にすると、時刻条件なしで due 判定する。"""

    @pytest.mark.parametrize(
        "frequency",
        ["毎日", "毎週", "毎月"],
    )
    def test_blank_run_time_means_due_at_any_time(self, frequency):
        """``取得時刻`` が空欄のときは、``run_time is None`` として「時刻条件なし」と解釈する。

        同じレポートを1日のうちいつ取っても中身が変わらない（例: 前日以前の確定済み
        データ）の用途を想定。「1時間ごと」では空欄を許さないので、この挙動は適用しない。
        """
        row = base_row(**{"取得頻度": frequency, "取得時刻": ""})
        rule = ScheduleRule.from_row(row)
        # 0:00 と 23:59 の両方で True を返す（=任意の時刻で due）
        assert rule.is_due(dt.datetime(2026, 1, 1, 0, 0)) is True  # noqa: DTZ001
        assert rule.is_due(dt.datetime(2026, 1, 1, 23, 59)) is True  # noqa: DTZ001

    def test_blank_run_time_still_respects_date_match(self):
        """``取得時刻`` が空欄でも、曜日や月の日など日付条件は引き続き適用される。"""
        # 「毎週・水曜」の行で、月曜に問い合わせると日付不一致で False
        row = base_row(
            **{
                "取得頻度": "毎週",
                "曜日": "水",
                "取得時刻": "",
            }
        )
        rule = ScheduleRule.from_row(row)
        # 2026/1/5 は月曜
        monday = dt.datetime(2026, 1, 5, 12, 0)  # noqa: DTZ001
        assert rule.is_due(monday) is False
        # 2026/1/7 は水曜
        wednesday = dt.datetime(2026, 1, 7, 12, 0)  # noqa: DTZ001
        assert rule.is_due(wednesday) is True


class TestNthBusinessDayParsing:
    """「第N営業日」のパース。"""

    def test_day_of_month_accepts_nth_business_day(self):
        """「日付」列に「第2営業日」と書いたとき、``nth_business_day`` が int になる。"""
        rule = ScheduleRule.from_row(base_row(取得頻度="毎月", 日付="第2営業日"))
        assert rule.nth_business_day == 2
        assert rule.day_of_month is None
        assert rule.month_end is False

    def test_day_of_month_accepts_nth_business_day_above_ten(self):
        """N が 10 以上の桁でも拾える。"""
        rule = ScheduleRule.from_row(base_row(取得頻度="毎月", 日付="第15営業日"))
        assert rule.nth_business_day == 15
        assert rule.day_of_month is None
        assert rule.month_end is False

    @pytest.mark.parametrize("text", ["第二営業日", "2営業日", "第2"])
    def test_invalid_nth_business_day_falls_back_to_int_parse(self, text):
        """正規表現に合う形以外は ``int()`` にフォールバックし、``ValueError`` がそのまま飛ぶ。"""
        # 「第二営業日」は漢数字なので正規表現不一致 → ``_parse_int`` → ``int()`` で失敗
        # 「2営業日」は「第」接頭辞が無いので正規表現不一致
        # 「第2」は「営業日」サフィックスが無いので正規表現不一致
        with pytest.raises(ValueError):
            ScheduleRule.from_row(base_row(取得頻度="毎月", 日付=text))


class TestNthBusinessDayIsDue:
    """``is_due()`` の「第N営業日」分岐を偽カレンダー経由で確認する。"""

    @staticmethod
    def _monthly_rule(date_marker: str) -> ScheduleRule:
        return ScheduleRule.from_row(
            base_row(
                **{
                    "取得頻度": "毎月",
                    "曜日": "",
                    "取得時刻": "",
                    "日付": date_marker,
                }
            )
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
