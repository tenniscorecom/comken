"""comken/toolbox/excel/sheet.py — Excel シートを操作する。"""

from copy import copy
from typing import TYPE_CHECKING, Any

from openpyxl.styles import Border, PatternFill, Side
from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from comken.exceptions import DataSheetAccessError
from comken.toolbox.excel.table import ExcelTable

if TYPE_CHECKING:
    from comken.toolbox.excel.workbook import Excel


class Sheet:
    """Excel シートのデータ領域または表示領域を操作する。"""

    def __init__(self, excel: "Excel", worksheet: Worksheet, data_prefix: str) -> None:
        self._excel = excel
        self._worksheet = worksheet
        self._data_prefix = data_prefix

    @property
    def is_data_sheet(self) -> bool:
        """プレフィックス付きのデータシートか返す。"""
        return self._worksheet.title.startswith(self._data_prefix)

    def table(self) -> ExcelTable:
        """データシート全体を扱うテーブルを返す。"""
        if not self.is_data_sheet:
            raise DataSheetAccessError(self._worksheet.title, "table")
        return ExcelTable(self._excel, self._worksheet)

    def write_value(self, cell: str, value: Any) -> None:
        """セルへ値を書き込む。"""
        self._ensure_display_sheet("write_value")
        self._worksheet[cell] = value
        self._excel._mark_dirty()

    def read_value(self, cell: str) -> Any:
        """セルの値を読む。"""
        self._ensure_display_sheet("read_value")
        return "" if self._worksheet[cell].value is None else self._worksheet[cell].value

    def write_formula(self, cell: str, formula: str) -> None:
        """セルへ数式を書き込む。"""
        self.write_value(cell, formula)

    def read_formula(self, cell: str) -> str:
        """セルの数式を読む。数式でなければ空文字を返す。"""
        value = self.read_value(cell)
        return value if isinstance(value, str) and value.startswith("=") else ""

    def write_range(self, cell_range: str, values: list[list[Any]]) -> None:
        """指定範囲へ二次元の値を書き込む。"""
        self._ensure_display_sheet("write_range")
        cells = self._worksheet[cell_range]
        if len(cells) != len(values) or any(
            len(row) != len(value_row) for row, value_row in zip(cells, values, strict=False)
        ):
            raise ValueError("指定範囲と values の行数・列数が一致しません。")
        for cell_row, value_row in zip(cells, values, strict=True):
            for cell, value in zip(cell_row, value_row, strict=True):
                cell.value = value
        self._excel._mark_dirty()

    def read_range(self, cell_range: str) -> list[dict[str, Any]]:
        """指定範囲の先頭行を見出しとして辞書のリストで読む。"""
        self._ensure_display_sheet("read_range")
        rows = [
            ["" if cell.value is None else cell.value for cell in row]
            for row in self._worksheet[cell_range]
        ]
        if not rows:
            return []
        headers = [str(value) for value in rows[0]]
        return [dict(zip(headers, row, strict=True)) for row in rows[1:]]

    def get_used_range(self) -> tuple[str, str]:
        """使用範囲の左上と右下のセル参照を返す。"""
        self._ensure_display_sheet("get_used_range")
        return "A1", f"{get_column_letter(self._worksheet.max_column)}{self._worksheet.max_row}"

    def set_row_height(self, row: int, height: float) -> None:
        """行の高さを設定する。"""
        self._ensure_display_sheet("set_row_height")
        self._worksheet.row_dimensions[row].height = height
        self._excel._mark_dirty()

    def set_column_width(self, col: str, width: float) -> None:
        """列の幅を設定する。"""
        self._ensure_display_sheet("set_column_width")
        self._worksheet.column_dimensions[col].width = width
        self._excel._mark_dirty()

    def hide_row(self, row: int) -> None:
        self._set_row_hidden(row, True)

    def show_row(self, row: int) -> None:
        self._set_row_hidden(row, False)

    def hide_column(self, col: str) -> None:
        self._set_column_hidden(col, True)

    def show_column(self, col: str) -> None:
        self._set_column_hidden(col, False)

    def insert_row(self, row: int) -> None:
        self._ensure_display_sheet("insert_row")
        self._worksheet.insert_rows(row)
        self._excel._mark_dirty()

    def delete_row(self, row: int) -> None:
        self._ensure_display_sheet("delete_row")
        self._worksheet.delete_rows(row)
        self._excel._mark_dirty()

    def insert_column(self, col: str) -> None:
        self._ensure_display_sheet("insert_column")
        self._worksheet.insert_cols(column_index_from_string(col))
        self._excel._mark_dirty()

    def delete_column(self, col: str) -> None:
        self._ensure_display_sheet("delete_column")
        self._worksheet.delete_cols(column_index_from_string(col))
        self._excel._mark_dirty()

    def format(self, cell: str, **kwargs: Any) -> None:
        """セルのフォントと表示形式を設定する。"""
        self._ensure_display_sheet("format")
        target = self._worksheet[cell]
        font_keys = {"bold", "italic", "size", "name", "color"}
        unknown = set(kwargs) - font_keys - {"number_format"}
        if unknown:
            raise TypeError(f"format() で使用できない引数です: {sorted(unknown)}")
        font = copy(target.font)
        for key, value in kwargs.items():
            if key in font_keys:
                setattr(font, key, value)
        target.font = font
        if "number_format" in kwargs:
            target.number_format = str(kwargs["number_format"])
        self._excel._mark_dirty()

    def set_background(self, cell: str, color: str) -> None:
        self._ensure_display_sheet("set_background")
        self._worksheet[cell].fill = PatternFill("solid", fgColor=color.removeprefix("#"))
        self._excel._mark_dirty()

    def set_border(self, cell: str, **kwargs: Any) -> None:
        self._ensure_display_sheet("set_border")
        style = str(kwargs.pop("style", "thin"))
        color = str(kwargs.pop("color", "000000")).removeprefix("#")
        if kwargs:
            raise TypeError(f"set_border() で使用できない引数です: {sorted(kwargs)}")
        side = Side(style=style, color=color)
        self._worksheet[cell].border = Border(left=side, right=side, top=side, bottom=side)
        self._excel._mark_dirty()

    def merge_cells(self, cell_range: str) -> None:
        self._ensure_display_sheet("merge_cells")
        self._worksheet.merge_cells(cell_range)
        self._excel._mark_dirty()

    def unmerge_cells(self, cell_range: str) -> None:
        self._ensure_display_sheet("unmerge_cells")
        self._worksheet.unmerge_cells(cell_range)
        self._excel._mark_dirty()

    def freeze_panes(self, cell: str) -> None:
        self._ensure_display_sheet("freeze_panes")
        self._worksheet.freeze_panes = cell
        self._excel._mark_dirty()

    def _ensure_display_sheet(self, operation: str) -> None:
        self._excel._ensure_open()
        if self.is_data_sheet:
            raise DataSheetAccessError(self._worksheet.title, operation)

    def _set_row_hidden(self, row: int, is_hidden: bool) -> None:
        self._ensure_display_sheet("hide/show_row")
        self._worksheet.row_dimensions[row].hidden = is_hidden
        self._excel._mark_dirty()

    def _set_column_hidden(self, col: str, is_hidden: bool) -> None:
        self._ensure_display_sheet("hide/show_column")
        self._worksheet.column_dimensions[col].hidden = is_hidden
        self._excel._mark_dirty()
