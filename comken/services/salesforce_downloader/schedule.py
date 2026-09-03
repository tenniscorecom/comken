"""comken/services/salesforce_downloader/schedule.py — 取得時刻を判定する。"""

import datetime as dt
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from comken.core.holidays import (
    BusinessDayNotFoundError,
    HolidayCalendar,
    default_calendar,
    nth_business_day_of_month,
)
from comken.exceptions import (
    DownloaderError,
    ScheduleDuplicateKeyError,
    ScheduleIntervalMissingError,
    ScheduleRequiredValueMissingError,
    ScheduleRowValueError,
    ScheduleWeekdayInvalidError,
    SheetNotFoundError,
    UnsupportedScheduleFrequencyError,
)
from comken.services.salesforce_downloader.report_master import (
    _FIRST_DATA_ROW,
    _is_blank,
    _to_bool,
    _to_time,
    read_raw_rows,
)

FREQUENCY_HOURLY = "1時間ごと"
FREQUENCY_DAILY = "毎日"
FREQUENCY_WEEKLY = "毎週"
FREQUENCY_MONTHLY = "毎月"
HOLIDAY_SKIP = "取得しない"
WEEKDAY_NAMES = ("月", "火", "水", "木", "金", "土", "日")

logger = logging.getLogger(__name__)

# 「第N営業日」表記の正規表現。N は 1 以上の整数。「曜日付き」（例: 「第2営業日（月曜）」）
# のような表記は受け付けず、もっとも素直な形の入力を要求する
_NTH_BUSINESS_DAY_PATTERN = re.compile(r"^第(\d+)営業日$")

# レポート管理表と同じブック内のスケジュール管理シート名。**管理表本体と
# 一緒に置かれる**ため、このシートが無い管理表でもエラーにせず空とみなす
# （後方互換。詳細は load_schedule() を参照）
SCHEDULE_SHEET_NAME = "スケジュール"


@dataclass(frozen=True)
class ScheduleRule:
    """取得スケジュール管理表の1行。"""

    schedule_key: str
    report_key: str
    frequency: str
    run_time: dt.time | None = None
    interval_minutes: int | None = None
    weekday: int | None = None
    day_of_month: int | None = None
    month_end: bool = False
    nth_business_day: int | None = None
    holiday_policy: str = HOLIDAY_SKIP
    enabled: bool = True

    @classmethod
    def from_row(cls, row: Mapping[str, object]) -> Self:
        """日本語カラム名の辞書からスケジュールを作る。"""
        day_of_month, month_end, nth_business_day = _parse_day_of_month(row.get("日付"))
        return cls(
            schedule_key=_required_text(row, "スケジュールキー"),
            report_key=_required_text(row, "レポートキー"),
            frequency=_required_text(row, "取得頻度"),
            run_time=_to_time(row.get("取得時刻")),
            interval_minutes=_parse_int(row.get("取得間隔（分）")),
            weekday=_parse_weekday(row.get("曜日")),
            day_of_month=day_of_month,
            month_end=month_end,
            nth_business_day=nth_business_day,
            holiday_policy=_text_or_default(row, "祝日対応", HOLIDAY_SKIP),
            enabled=_to_bool(row.get("有効")),
        )

    def is_due(
        self,
        now: dt.datetime,
        *,
        holidays: set[dt.date] | frozenset[dt.date] = frozenset(),
        calendar: HolidayCalendar | None = None,
    ) -> bool:
        """指定時刻にこのスケジュールを実行すべきか判定する。

        ``calendar`` は「日付」列に「第N営業日」を指定した行の判定にのみ使う
        （``comken.core.holidays.nth_business_day_of_month`` に渡す）。省略時は
        ``default_calendar()`` にフォールバックする。``holidays`` 引数（祝日の
        ``set[date]``）は独立に残しており、「第N営業日」以外での祝日判定に使う。

        ``FREQUENCY_DAILY`` / ``FREQUENCY_WEEKLY`` / ``FREQUENCY_MONTHLY`` で
        ``run_time is None`` のときは「時刻条件なし」を意味し、日付条件が合えば常に
        ``True`` を返す（例: 前日以前の確定済みデータのように、いつ取っても同じ内容の
        レポート用）。``FREQUENCY_HOURLY`` は対象外で、``run_time`` が無いと
        ``ScheduleIntervalMissingError`` を投げる。
        """
        if not self.enabled or not self._date_matches(now.date(), holidays, calendar):
            return False
        if self.frequency == FREQUENCY_HOURLY:
            return self._is_hourly_due(now)
        if self.frequency in {FREQUENCY_DAILY, FREQUENCY_WEEKLY, FREQUENCY_MONTHLY}:
            return self.run_time is None or now.time() >= self.run_time
        raise UnsupportedScheduleFrequencyError(self.frequency)

    def _date_matches(
        self,
        date: dt.date,
        holidays: set[dt.date] | frozenset[dt.date],
        calendar: HolidayCalendar | None = None,
    ) -> bool:
        if self.holiday_policy == HOLIDAY_SKIP and date in holidays:
            return False
        if self.weekday is not None and date.weekday() != self.weekday:
            return False
        if self.day_of_month is not None and date.day != self.day_of_month:
            return False
        if self.nth_business_day is not None:
            cal = calendar if calendar is not None else default_calendar()
            try:
                target = nth_business_day_of_month(
                    date.replace(day=1), self.nth_business_day, calendar=cal
                )
            except BusinessDayNotFoundError:
                # 「第N営業日」がその月の営業日数を超える設定ミスのケース。
                # ここで呼び出し元（``download_scheduled``）全体を止めると、
                # 同じ管理表内の他レポートの取得まで巻き添えになるため、
                # この日は対象外として扱いログだけ残す
                logger.warning(
                    "スケジュール %s の「第%d営業日」指定が %s年%s月の営業日数を"
                    "超えています。この日は対象外として扱います。",
                    self.schedule_key,
                    self.nth_business_day,
                    date.year,
                    date.month,
                )
                return False
            if date != target:
                return False
        return not self.month_end or (date + dt.timedelta(days=1)).month != date.month

    def _is_hourly_due(self, now: dt.datetime) -> bool:
        if self.run_time is None or not self.interval_minutes:
            raise ScheduleIntervalMissingError()
        if now.time() < self.run_time:
            return False
        start_minutes = self.run_time.hour * 60 + self.run_time.minute
        now_minutes = now.hour * 60 + now.minute
        return (now_minutes - start_minutes) % self.interval_minutes == 0


def _required_text(row: Mapping[str, object], column: str) -> str:
    value = str(row.get(column, "")).strip()
    if not value:
        raise ScheduleRequiredValueMissingError(column)
    return value


def _text_or_default(row: Mapping[str, object], column: str, default: str) -> str:
    value = str(row.get(column, "")).strip()
    return value or default


def _parse_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    return int(str(value).strip())


def _parse_day_of_month(value: object) -> tuple[int | None, bool, int | None]:
    """「日付」列を ``(day_of_month, month_end, nth_business_day)`` に分解する。

    空欄は「指定なし」、数字 1〜31 は ``day_of_month``、文字列「月末」は
    ``month_end=True``、``"第N営業日"``（N は 1 以上の整数）は
    ``nth_business_day=N`` として扱う。``_parse_int`` と同じ緩さで解釈し、
    想定外の値（例: ``"来月"``）は ``int()`` 由来の ``ValueError`` をそのまま
    投げる（専用のエラー型は用意しない）。

    Returns:
        3 要素のタプル。常にどれか 1 つだけが立ち、残りは「指定なし」になる。
    """
    if value in (None, ""):
        return None, False, None
    text = str(value).strip()
    if text == "月末":
        return None, True, None
    match = _NTH_BUSINESS_DAY_PATTERN.match(text)
    if match:
        return None, False, int(match.group(1))
    return _parse_int(text), False, None


def _parse_weekday(value: object) -> int | None:
    if value in (None, ""):
        return None
    text = str(value).strip().removesuffix("曜日")
    if text not in WEEKDAY_NAMES:
        raise ScheduleWeekdayInvalidError(value)
    return WEEKDAY_NAMES.index(text)


def load_schedule(path: str | Path | None = None) -> list[ScheduleRule]:
    """スケジュール管理シートを読んで、``ScheduleRule`` のリストを返す。

    **シートが存在しない場合はエラーにせず空リストを返す。** この機能を
    使っていない既存の管理表（「スケジュール」シートをまだ追加していないもの）が、
    このシートの有無で読み込みごと壊れないようにするため（後方互換）。

    空行は読み飛ばす（``ReportEntry`` と同じ扱い）。**スケジュールキーが
    重複している行はエラー**にする（``ReportEntry.key`` が ``unique=True``
    であるのと同じ考え方）。**行の中で値が壊れていた場合**は、``ScheduleRule.from_row``
    が投げた例外を ``ScheduleRowValueError`` で受け直して**行番号付き**で
    再送出する（業務担当者がどの行を直せばいいか分かるようにするため）。

    存在しない ``レポートキー`` を指している行はここではエラーにしない。
    レポート管理表との突き合わせは呼び出し側 ``download_scheduled()`` の責務。

    Args:
        path: 管理表（Excel）のパス。``None`` のときは ``MASTER_PATH``。

    Returns:
        宣言順に並んだ ``ScheduleRule`` のリスト。

    Raises:
        ScheduleDuplicateKeyError: スケジュールキーが重複している行がある。
        ScheduleRowValueError: 値の整合性エラー（行番号付き）。
        ExcelFileNotFoundError: ``path`` が存在しない場合。
    """
    if path is None:
        from comken.services.salesforce_downloader._paths import MASTER_PATH

        path = MASTER_PATH
    source = Path(path)

    # **シートが無い場合は空リストを返す。** この機能をまだ使っていない管理表を
    # 読み込み時に壊さないため。``ExcelFileNotFoundError`` などの「ファイル自体に
    # 関するエラー」はそのまま上位へ伝える
    try:
        raw_rows = read_raw_rows(source, SCHEDULE_SHEET_NAME)
    except SheetNotFoundError:
        return []

    rules: list[ScheduleRule] = []
    seen_keys: set[str] = set()
    for offset, raw in enumerate(raw_rows):
        if _is_blank(raw):
            continue  # 表の下に残った空行は読み飛ばす
        row_number = offset + _FIRST_DATA_ROW
        try:
            rule = ScheduleRule.from_row(raw)
        except DownloaderError as e:
            # ``ScheduleDuplicateKeyError`` も ``DownloaderError`` のサブクラスだが
            # この時点ではまだ送出される経路が無い（``from_row`` は送らない）ので
            # そのまま行番号を足して再送出する
            raise ScheduleRowValueError(row_number, str(e)) from e
        if rule.schedule_key in seen_keys:
            raise ScheduleDuplicateKeyError(rule.schedule_key, row_number, source)
        seen_keys.add(rule.schedule_key)
        rules.append(rule)
    return rules


__all__ = [
    "ScheduleRule",
    "SCHEDULE_SHEET_NAME",
    "load_schedule",
]
