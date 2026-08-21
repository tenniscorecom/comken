"""comken/toolbox/holidays/sources/master_table.py — 社内管理表の「会社休日」ソース。

社内管理表（Excel）の **「会社休日」シート** から、内閣府の CSV にない
会社独自の休業日（創立記念日・年末年始の臨時休業など）を読み取る。

内閣府の CSV とマージして使う前提で、``HolidayCalendar.from_sources`` に
``CabinetOfficeCsvSource`` と一緒に渡すのを主な使い方とする。

読み取りは ``comken.toolbox.excel.Excel`` を使い、
「日付」「名称」の列を必須とする。列が無いシートは
``HolidayCalendarSourceError`` で止める（誤って別のシートを読まないため）。
"""

import datetime as _dt
import logging
from collections.abc import Mapping, Sequence
from pathlib import Path

from comken.exceptions import HolidayCalendarSourceError
from comken.toolbox.excel import Excel
from comken.toolbox.holidays.calendar import Holiday, HolidaySource

logger = logging.getLogger(__name__)

# 読み取るシート名（既定）
DEFAULT_SHEET_NAME = "会社休日"
# 読み取る列の日本語見出し
DATE_COLUMN_HEADER = "日付"
NAME_COLUMN_HEADER = "名称"


class ComkenMasterTableSource(HolidaySource):
    """社内管理表の「会社休日」シートを読んで ``Holiday`` の iterable を返す。

    Args:
        path: 管理表（Excel）のパス。
        sheet_name: 読み取り対象のシート名。既定は ``"会社休日"``。
        date_column: 日付が入っている列の見出し。既定は ``"日付"``。
        name_column: 名称が入っている列の見出し。既定は ``"名称"``。
    """

    def __init__(
        self,
        path: Path | str,
        *,
        sheet_name: str = DEFAULT_SHEET_NAME,
        date_column: str = DATE_COLUMN_HEADER,
        name_column: str = NAME_COLUMN_HEADER,
    ) -> None:
        self._path = Path(path)
        self._sheet_name = sheet_name
        self._date_column = date_column
        self._name_column = name_column

    def load(self) -> list[Holiday]:
        """管理表から会社休日を読み取り、``Holiday`` のリストを返す。"""
        if not self._path.exists():
            raise HolidayCalendarSourceError(
                str(self._path),
                "管理表のファイルが存在しません。パスが正しいか確認してください。",
            )
        try:
            # 既存の管理表は data_ プレフィックスを使っていないため、このブックでは
            # すべてのシートをデータシートとして扱う。
            with Excel(self._path, data_prefix="") as excel:
                rows = excel.sheet(self._sheet_name).table().read()
        except Exception as error:  # SheetNotFoundError 等をまとめて拾う
            raise HolidayCalendarSourceError(
                str(self._path),
                f"シート「{self._sheet_name}」を読み取れません: {error}",
            ) from error

        return _rows_to_holidays(
            rows,
            path=self._path,
            sheet_name=self._sheet_name,
            date_column=self._date_column,
            name_column=self._name_column,
        )


def _rows_to_holidays(
    rows: Sequence[Mapping[str, object]],
    *,
    path: Path,
    sheet_name: str,
    date_column: str,
    name_column: str,
) -> list[Holiday]:
    """Excel から読んだ行の dict を ``Holiday`` のリストに変換する。"""
    if not rows:
        raise HolidayCalendarSourceError(
            str(path),
            f"シート「{sheet_name}」にデータ行がありません。"
            f"「{date_column}」と「{name_column}」の列があるか確認してください。",
        )

    first_row = rows[0]
    missing = [column for column in (date_column, name_column) if column not in first_row]
    if missing:
        raise HolidayCalendarSourceError(
            str(path),
            f"シート「{sheet_name}」に必須列がありません: {' / '.join(missing)}",
        )

    holidays: list[Holiday] = []
    for row_index, row in enumerate(rows, start=2):
        raw_date = row.get(date_column)
        if raw_date in (None, ""):
            # 空行は黙って飛ばす（テンプレートの記入例などが混ざることを想定）
            continue
        parsed_date = _to_date(raw_date)
        if parsed_date is None:
            raise HolidayCalendarSourceError(
                str(path),
                f"シート「{sheet_name}」{row_index} 行目の日付を解釈できません: {raw_date!r}",
            )
        name = row.get(name_column)
        if not isinstance(name, str) or not name.strip():
            raise HolidayCalendarSourceError(
                str(path),
                f"シート「{sheet_name}」{row_index} 行目の名称が空です。",
            )
        holidays.append(Holiday(date=parsed_date, name=name.strip()))

    if not holidays:
        raise HolidayCalendarSourceError(
            str(path),
            f"シート「{sheet_name}」から有効な祝日を読み取れませんでした。",
        )

    return sorted(holidays, key=lambda h: h.date)


def _to_date(value: object) -> _dt.date | None:
    """Excel のセル値を ``date`` に変換する。失敗したら ``None``。"""
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    if isinstance(value, str):
        text = value.strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日"):
            try:
                return _dt.datetime.strptime(text, fmt).date()  # noqa: DTZ007  # 業務日付として naive で扱う
            except ValueError:
                continue
    return None


__all__ = [
    "ComkenMasterTableSource",
    "DEFAULT_SHEET_NAME",
    "DATE_COLUMN_HEADER",
    "NAME_COLUMN_HEADER",
]
