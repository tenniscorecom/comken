"""comken/toolbox/excel/table.py — Excel データシートを操作する。"""

from datetime import datetime
from typing import TYPE_CHECKING, TypeAlias

from openpyxl.utils.cell import range_boundaries
from openpyxl.worksheet.worksheet import Worksheet

from comken.core.table.model import Table
from comken.exceptions import (
    DuplicateHeaderCellError,
    EmptyHeaderCellError,
    InvalidTableOperationError,
)

if TYPE_CHECKING:
    from comken.toolbox.excel.workbook import Excel

Value: TypeAlias = str | int | float | bool | datetime


class ExcelTable:
    """データシート全体を1つのテーブルとして操作する。

    Sheet の表示操作と分けることで、表データの読み書きがレイアウト変更へ
    意図せず影響されないようにしている。
    """

    def __init__(self, excel: "Excel", worksheet: Worksheet, name: str | None = None) -> None:
        self._excel = excel
        self._worksheet = worksheet
        self._name = name

    def read(self) -> Table:
        """Excelテーブルの実際の定義範囲だけを読み、値を返す。

        シートの使用範囲ではなく Excel が保持する ``ref`` を使うため、表の外に
        ある無関係なセルを現在の Table に混ぜません。
        """
        self._excel._ensure_open()
        if self._name is None:
            table_names = list(self._worksheet.tables)
            if len(table_names) != 1:
                raise InvalidTableOperationError("対象テーブルを一意に決められません。")
            self._name = table_names[0]
        excel_table = self._worksheet.tables[self._name]
        min_col, min_row, max_col, max_row = range_boundaries(excel_table.ref)
        formula_cells = [
            cell
            for row in self._worksheet.iter_rows(
                min_row=min_row + 1, max_row=max_row, min_col=min_col, max_col=max_col
            )
            for cell in row
            if isinstance(cell.value, str) and cell.value.startswith("=")
        ]
        if formula_cells:
            return self._excel._read_table_with_com(
                self._worksheet.title, min_col, min_row, max_col, max_row
            )
        rows = [
            tuple(cell.value for cell in row)
            for row in self._worksheet.iter_rows(
                min_row=min_row, max_row=max_row, min_col=min_col, max_col=max_col
            )
        ]
        if not rows or all(value is None for value in rows[0]):
            return Table([], [])
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
        result = [
            {
                str(header): (
                    ""
                    if value is None
                    else value
                    if str(header) in self._excel._types
                    else str(value)
                )
                for header, value in zip(headers, row[:last_column], strict=True)
            }
            for row in rows[1:]
            if any(value is not None for value in row[:last_column])
        ]
        return Table([str(header) for header in headers], result, types=self._excel._types)

    def replace(self, rows: list[dict[str, Value]] | Table) -> None:
        """データシート全体を置き換える。"""
        self._excel._ensure_writable("replace")
        if self._name is None:
            names = list(self._worksheet.tables)
            if len(names) != 1:
                raise InvalidTableOperationError("書き込み対象テーブルを一意に決められません。")
            self._name = names[0]
        excel_table = self._worksheet.tables[self._name]
        min_col, min_row, max_col, max_row = range_boundaries(excel_table.ref)
        table = rows if isinstance(rows, Table) else Table(list(rows[0]) if rows else [], rows)
        rows = table.read()
        headers = table.columns or [
            str(self._worksheet.cell(min_row, column).value or "")
            for column in range(min_col, max_col + 1)
        ]
        if not any(headers):
            raise InvalidTableOperationError("列のないTableはExcelテーブルにできません。")
        for column, header in enumerate(headers, min_col):
            self._worksheet.cell(row=min_row, column=column, value=header)
        self._clear_removed_cells(
            min_col=min_col,
            min_row=min_row,
            old_max_col=max_col,
            old_max_row=max_row,
            header_count=len(headers),
            row_count=len(rows),
        )
        for row_number, row in enumerate(rows, min_row + 1):
            for column, header in enumerate(headers, min_col):
                self._worksheet.cell(row=row_number, column=column, value=row.get(header, ""))
        new_max_row = min_row + max(len(rows), 1)
        last_cell = self._worksheet.cell(new_max_row, min_col + len(headers) - 1).coordinate
        excel_table.ref = f"{self._worksheet.cell(min_row, min_col).coordinate}:{last_cell}"
        self._excel._mark_dirty()

    def write(self, table: Table) -> None:
        """Tableをデータシートへ書き込む。保存はExcelの契約に従う。"""
        self.replace(table)

    def count(self) -> int:
        """データ行数を返す。"""
        return len(self.read())

    def _clear_removed_cells(
        self,
        *,
        min_col: int,
        min_row: int,
        old_max_col: int,
        old_max_row: int,
        header_count: int,
        row_count: int,
    ) -> None:
        """置換後の実テーブル範囲から外れる旧セルを空にする。"""
        for column in range(min_col + header_count, old_max_col + 1):
            self._worksheet.cell(row=min_row, column=column).value = None
        new_max_row = min_row + max(row_count, 1)
        for row_number in range(min_row + 1, max(old_max_row, new_max_row) + 1):
            for column in range(min_col, old_max_col + 1):
                if row_number > min_row + row_count or column >= min_col + header_count:
                    self._worksheet.cell(row=row_number, column=column).value = None
