"""comken/toolbox/excel/table.py — Excel データシートを操作する。"""

from datetime import datetime
from typing import TYPE_CHECKING, TypeAlias

from openpyxl.worksheet.worksheet import Worksheet

from comken.exceptions import DuplicateHeaderCellError, EmptyHeaderCellError

if TYPE_CHECKING:
    from comken.toolbox.excel.workbook import Excel

Value: TypeAlias = str | int | float | bool | datetime


class ExcelTable:
    """データシート全体を1つのテーブルとして操作する。"""

    def __init__(self, excel: "Excel", worksheet: Worksheet) -> None:
        self._excel = excel
        self._worksheet = worksheet

    def read(self) -> list[dict[str, Value]]:
        """データシート全体を辞書のリストで読む。"""
        self._excel._ensure_open()
        rows = list(self._worksheet.iter_rows(values_only=True))
        if not rows or all(value is None for value in rows[0]):
            return []
        last_column = max(
            (index for row in rows for index, value in enumerate(row, 1) if value is not None),
            default=0,
        )
        headers = list(rows[0][:last_column])
        empty_columns = [index for index, header in enumerate(headers, 1) if header is None]
        if empty_columns:
            raise EmptyHeaderCellError(empty_columns)
        duplicate_headers = [
            header for header in dict.fromkeys(headers) if headers.count(header) > 1
        ]
        if duplicate_headers:
            raise DuplicateHeaderCellError(duplicate_headers)
        return [
            {
                str(header): "" if value is None else value
                for header, value in zip(headers, row[:last_column], strict=True)
            }
            for row in rows[1:]
            if any(value is not None for value in row[:last_column])
        ]

    def replace(self, rows: list[dict[str, Value]]) -> None:
        """データシート全体を置き換える。"""
        self._excel._ensure_writable("replace")
        self._worksheet.delete_rows(1, self._worksheet.max_row)
        if rows:
            headers = list(rows[0])
            for column, header in enumerate(headers, 1):
                self._worksheet.cell(row=1, column=column, value=header)
            for row_number, row in enumerate(rows, 2):
                for column, header in enumerate(headers, 1):
                    self._worksheet.cell(row=row_number, column=column, value=row.get(header, ""))
        self._excel._mark_dirty()

    def count(self) -> int:
        """データ行数を返す。"""
        return len(self.read())
