"""comken/services/salesforce_downloader/sheets/schedule.py — スケジュール列と取得時刻の判定。

`sheets/` の他のファイルと同じく、**このファイルは「スケジュール」シートに何が
あるか（`ScheduleRule`）と、その値を使った判定ロジックを持つ**。Excel を読む・
雛形を作る仕組みは `report_master.py`（`sheets/` の外）にある。
"""

import datetime as dt
import logging
import re
from dataclasses import MISSING, dataclass
from pathlib import Path

from comken.core.holidays import (
    BusinessDayNotFoundError,
    HolidayCalendar,
    default_calendar,
    nth_business_day_of_month,
)
from comken.exceptions import (
    ExcelFileNotFoundError,
    ScheduleIntervalMissingError,
    ScheduleWeekdayInvalidError,
    SheetNotFoundError,
    UnsupportedScheduleFrequencyError,
)
from comken.services.salesforce_downloader.report_master import MasterRow, column

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


@dataclass(frozen=True, kw_only=True)
class ScheduleRule(MasterRow):
    """「スケジュール」シートの1行。1行 = 1つの取得ルール。

    列定義は `column()` に集約されている。``曜日`` / ``日付`` 列は自由記述
    （空欄を許す）なので ``choices`` を付けず、``weekday`` /
    ``day_of_month`` / ``month_end`` / ``nth_business_day`` の 4 つの
    `@property` でパース結果だけを公開する（``ReportEntry.report_id`` が
    URL から計算派生するのと同じ考え方）。

    Attributes:
        schedule_key: 列「スケジュールキー」。このルールを一意に識別するキー。
            履歴の「スケジュールキー」列に記録され、同じ行を同日に何度も
            実行しないための dedup 判定にも使う。
        report_key: 列「レポートキー」。対象のレポートの管理番号
            （レポート管理表シートの ID と対応する）。
        frequency: 列「取得頻度」。`FREQUENCY_HOURLY` / `FREQUENCY_DAILY` /
            `FREQUENCY_WEEKLY` / `FREQUENCY_MONTHLY` のいずれか。
        run_time: 列「取得時刻」。毎日・毎週・毎月・1時間ごとに共通の実行時刻
            （1時間ごとのときは開始時刻を兼ねる）。空欄可。
        raw_weekday: 列「曜日」。`frequency` が毎週のときだけ使う
            （下の `weekday` property で 0=月〜6=日 に変換）。
        raw_day_of_month: 列「日付」。`frequency` が毎月のときだけ使う
            （1〜31 の数字 / `月末` / `第N営業日` のいずれかを下の
            `day_of_month` / `month_end` / `nth_business_day` property で
            分解する）。
        holiday_policy: 列「祝日対応」。`HOLIDAY_SKIP`（既定）なら祝日はスキップする。
        enabled: 列「有効」。`○`/`×`。既定値なし（書き忘れはエラー）。
    """

    SHEET_NAME = SCHEDULE_SHEET_NAME

    schedule_key: str = column(
        "スケジュールキー",
        unique=True,
        help="このルールを一意に識別するキー。履歴の「スケジュールキー」列に記録され、"
        "同じスケジュール行を同日に何度も実行しない dedup 判定に使います",
    )
    report_key: str = column(
        "レポートキー",
        help="対象のレポートの管理番号（レポート管理表シートの ID と対応させる）",
    )
    frequency: str = column(
        "取得頻度",
        choices=(FREQUENCY_HOURLY, FREQUENCY_DAILY, FREQUENCY_WEEKLY, FREQUENCY_MONTHLY),
        help="1時間ごと / 毎日 / 毎週 / 毎月 のいずれか",
    )
    run_time: dt.time | None = column(
        "取得時刻",
        default=None,
        help="毎日・毎週・毎月・1時間ごとに共通の実行開始時刻。"
        "1時間ごとのときは開始時刻を兼ねる。空欄可",
    )
    # `choices` ではなく `default=""` の自由記述にしているのは空欄を許すため。
    # パース結果は下の `weekday` property で取り出す
    raw_weekday: str = column(
        "曜日",
        default="",
        help=(
            "frequency が「毎週」のときだけ書く。"
            "月〜日の漢字1文字（「月 / 火 / 水 / 木 / 金 / 土 / 日」のいずれか、"
            "または「曜日」を付ける形式（例: 「月曜日」））。空欄可"
        ),
    )
    raw_day_of_month: str = column(
        "日付",
        default="",
        help="frequency が「毎月」のときだけ書く。"
        "1〜31 の数字 / 「月末」 / 「第N営業日」（N は 1 以上の整数）のいずれか。"
        "空欄可",
    )
    holiday_policy: str = column(
        "祝日対応",
        default=HOLIDAY_SKIP,
        help="「取得しない」以外も自由に書ける（運用メモとしての利用を想定）",
    )
    # 既定値を持たせない（書き忘れを「有効」と区別するため）。`master.py` の
    # 「有効」列と同じ考え方
    enabled: bool = column(
        "有効",
        choices=("○", "×"),
        help="「○」か「×」と書いてください",
    )

    @property
    def weekday(self) -> int | None:
        """「曜日」列の値を 0=月〜6=日 の整数に変換する。空欄は None。

        Raises:
            ScheduleWeekdayInvalidError: 想定外の文字列が書かれている場合。
        """
        if not self.raw_weekday:
            return None
        text = self.raw_weekday.strip().removesuffix("曜日")
        if text not in WEEKDAY_NAMES:
            raise ScheduleWeekdayInvalidError(self.raw_weekday)
        return WEEKDAY_NAMES.index(text)

    @property
    def day_of_month(self) -> int | None:
        """「日付」列が 1〜31 の数字で書かれたとき、その値。"""
        _, value, _ = self._parsed_day_of_month
        return value

    @property
    def month_end(self) -> bool:
        """「日付」列が「月末」のとき True。"""
        value, _, _ = self._parsed_day_of_month
        return value

    @property
    def nth_business_day(self) -> int | None:
        """「日付」列が「第N営業日」のとき、N。"""
        _, _, value = self._parsed_day_of_month
        return value

    @property
    def _parsed_day_of_month(self) -> tuple[bool, int | None, int | None]:
        """「日付」列を ``(month_end, day_of_month, nth_business_day)`` に分解する。

        `ReportEntry.report_id` と同じく、Excel の生セル値を 1 回パースして
        3 つの派生プロパティへ分配する。空欄は「指定なし」、数字 1〜31 は
        `day_of_month`、文字列「月末」は `month_end=True`、`"第N営業日"` は
        `nth_business_day=N` として扱う。想定外の値（例: `"来月"`）は
        ``int()`` 由来の ``ValueError`` がそのまま飛ぶ（専用のエラー型は
        用意しない）。
        """
        return _parse_day_of_month(self.raw_day_of_month)

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
        """``run_time`` から 60 分刻みで一致するかを返す。

        ``interval_minutes`` 列は廃止し、判定は 60 分固定。``run_time`` が無い
        行は ``ScheduleIntervalMissingError``（「1時間ごとには開始時刻が必要」）
        を投げる。
        """
        if self.run_time is None:
            raise ScheduleIntervalMissingError()
        if now.time() < self.run_time:
            return False
        start_minutes = self.run_time.hour * 60 + self.run_time.minute
        now_minutes = now.hour * 60 + now.minute
        return (now_minutes - start_minutes) % 60 == 0


def _parse_day_of_month(value: object) -> tuple[bool, int | None, int | None]:
    """「日付」列を ``(month_end, day_of_month, nth_business_day)`` に分解する。

    空欄は「指定なし」、数字 1〜31 は ``day_of_month``、文字列「月末」は
    ``month_end=True``、``"第N営業日"``（N は 1 以上の整数）は
    ``nth_business_day=N`` として扱う。``_parse_int`` と同じ緩さで解釈し、
    想定外の値（例: ``"来月"``）は ``int()`` 由来の ``ValueError`` をそのまま
    投げる（専用のエラー型は用意しない）。

    Returns:
        3 要素のタプル。常にどれか 1 つだけが立ち、残りは「指定なし」になる。
    """
    if value in (None, ""):
        return False, None, None
    text = str(value).strip()
    if text == "月末":
        return True, None, None
    match = _NTH_BUSINESS_DAY_PATTERN.match(text)
    if match:
        return False, None, int(match.group(1))
    if not text.isdigit():
        raise ValueError(f"「日付」列の値を解釈できません: {value!r}")
    return False, int(text), None


def load_schedule(path: str | Path | None = None) -> list[ScheduleRule]:
    """スケジュール管理シートを読んで、``ScheduleRule`` のリストを返す。

    **シートが存在しない場合はエラーにせず空リストを返す。** この機能を
    使っていない既存の管理表（「スケジュール」シートをまだ追加していないもの）が、
    このシートの有無で読み込みごと壊れないようにするため（後方互換）。

    ``ScheduleRule.load()`` が `unique=True` の列で重複を検出すると
    ``MasterDuplicateValueError`` を上げ、必須列が空だと
    ``MasterRowValueError`` を上げる。これらは `comken/exceptions/master_table.py`
    の例外で、メッセージに**行番号・列名・値**が入る（業務担当者が表の
    どこを直せばいいか分かる形式）。

    存在しない ``レポートキー`` を指している行はここではエラーにしない。
    レポート管理表との突き合わせは呼び出し側 ``download_scheduled()`` の責務。

    Args:
        path: 管理表（Excel）のパス。``None`` のときは ``MASTER_PATH``。

    Returns:
        宣言順に並んだ ``ScheduleRule`` のリスト。

    Raises:
        MasterColumnNotFoundError: 宣言した見出しが表に無い場合。
        MasterRowValueError: 値が型・選択肢に合わない、または空にできない列が空の場合。
        MasterDuplicateValueError: スケジュールキーが重複している行がある場合。
        ExcelFileNotFoundError: ``path`` が存在しない場合。
    """
    if path is None:
        from comken.services.salesforce_downloader.paths import MASTER_PATH

        path = MASTER_PATH
    source = Path(path)
    # **シートが無い場合は空リストを返す。** この機能をまだ使っていない管理表を
    # 読み込み時に壊さないため。``ExcelFileNotFoundError`` などの「ファイル自体に
    # 関するエラー」はそのまま上位へ伝える
    try:
        return ScheduleRule.load(source)
    except SheetNotFoundError:
        return []


# ドロップダウンを適用する行数（見出しの次の行から）。あとから行を足しても
# 効くよう、十分な行数を確保する（雛形生成があった頃の既定値を踏襲）
_DROPDOWN_ROW_COUNT = 1000


def apply_schedule_dropdowns(path: str | Path) -> None:
    """既存の「スケジュール」シートの列に、Excel のドロップダウン（入力規則）を付ける。

    **シート自体は作らない。** 「スケジュール」シートは手で作る運用のため、
    ここでは既にあるシートに対して入力規則だけを追加・上書きする。見出し行
    （1行目）を読んで列位置を探すので、列の並び順は問わない。

    ドロップダウンを付ける対象は `ScheduleRule._columns()` から動的に拾う
    （``choices`` が宣言された列）。`祝日対応` は自由記述のため対象外
    （意図的。「取得しない」以外は「祝日でも取得する」という自由な表現を許す）。

    Args:
        path: 「スケジュール」シートを持つ Excel ファイル（既存）。

    Raises:
        ExcelFileNotFoundError: ``path`` が存在しない場合。
        SheetNotFoundError: 「スケジュール」シートが無い場合。
    """
    from openpyxl import load_workbook
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    source = Path(path)
    if not source.exists():
        raise ExcelFileNotFoundError(source)
    book = load_workbook(source)
    if SCHEDULE_SHEET_NAME not in book.sheetnames:
        raise SheetNotFoundError(SCHEDULE_SHEET_NAME, book.sheetnames)
    sheet = book[SCHEDULE_SHEET_NAME]

    last_row = 1 + _DROPDOWN_ROW_COUNT
    applied = 0
    # 列宣言 (`_columns()`) から {見出し: choices} を組み立て、見出し名でシートに
    # 存在する列だけにドロップダウンを当てる。`_SCHEDULE_DROPDOWN_CHOICES` のような
    # 別辞書を二重管理しないので、`column()` の宣言を足せば自動でドロップダウンが
    # 付く（master.py の `ReportEntry.create_template()` と同じ「宣言1か所」原則）
    choices_by_header: dict[str, tuple[str, ...]] = {
        spec.header: spec.choices
        for _, spec, _ in ScheduleRule._columns()
        if spec.choices
    }
    # 既定値のない列は `allow_blank=False` にする（ドロップダウンからの空欄提出を
    # 許さない）。既定値の有無は dataclass の `default` 属性から取る
    allow_blank_by_header: dict[str, bool] = {
        spec.header: _is_optional(name)
        for name, spec, _ in ScheduleRule._columns()
    }
    header_row = next(sheet.iter_rows(min_row=1, max_row=1))
    for column_index, cell in enumerate(header_row, start=1):
        header = str(cell.value) if cell.value is not None else ""
        choices = choices_by_header.get(header)
        if choices is None:
            continue
        letter = get_column_letter(column_index)
        validation = DataValidation(
            type="list",
            formula1=f'"{",".join(choices)}"',
            allow_blank=allow_blank_by_header.get(header, False),
            showDropDown=False,
            showErrorMessage=True,
            errorTitle="書き方が違います",
            error=f"『{'』か『'.join(choices)}』のいずれかを入力してください。",
        )
        validation.add(f"{letter}2:{letter}{last_row}")
        sheet.add_data_validation(validation)
        applied += 1

    book.save(source)
    book.close()
    logger.debug(
        "スケジュールシートへドロップダウンを適用しました: path=%s, 列数=%d", source, applied
    )


def _is_optional(name: str) -> bool:
    """`ScheduleRule` のフィールドが既定値を持つか（空欄を許すか）。"""
    for field_name, item in ScheduleRule.__dataclass_fields__.items():
        if field_name == name:
            return item.default is not MISSING
    return False


__all__ = [
    "ScheduleRule",
    "SCHEDULE_SHEET_NAME",
    "load_schedule",
    "apply_schedule_dropdowns",
]
