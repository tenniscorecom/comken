"""comken/toolbox/excel/workbook.py — Excel ブックとデータ領域を操作する。"""

from copy import copy
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self, TypeAlias, cast

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Border, PatternFill, Side
from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from comken.exceptions import (
    DataSheetAccessError,
    DuplicateHeaderCellError,
    EmptyHeaderCellError,
    SheetNotFoundError,
)

Value: TypeAlias = str | int | float | bool | datetime
_EXCEL_SUFFIXES = {".xlsx", ".xlsm", ".xltx", ".xltm"}


class Excel:
    """Excel ワークブックを開き、シート単位の操作を提供する。"""

    def __init__(self, source: str | Path, *, data_prefix: str = "data_") -> None:
        self.path = Path(source)
        self._data_prefix = data_prefix
        self._is_closed = False
        self._is_dirty = False
        if self.path.exists():
            self._workbook = load_workbook(
                self.path,
                keep_vba=self.path.suffix.casefold() in {".xlsm", ".xltm"},
            )
        else:
            self._workbook = Workbook()

    def __enter__(self) -> Self:
        self._ensure_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close(save=exc_type is None)

    def sheet(self, name: str) -> "Sheet":
        """名前でシートを取得する。未存在の新規ブックでは最初のシートを改名する。"""
        self._ensure_open()
        if name not in self._workbook.sheetnames:
            if not self.path.exists() and self._is_pristine_workbook():
                cast(Worksheet, self._workbook.active).title = name
                self._is_dirty = True
            else:
                raise SheetNotFoundError(name, self._workbook.sheetnames)
        return Sheet(self, self._workbook[name], self._data_prefix)

    def list_data_sheets(self) -> list[str]:
        """データシート名をブック内の順序で返す。"""
        self._ensure_open()
        return [name for name in self._workbook.sheetnames if name.startswith(self._data_prefix)]

    def close(self, *, save: bool = True) -> None:
        """変更を保存してワークブックを閉じる。"""
        if self._is_closed:
            return
        if save and self._is_dirty:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._workbook.save(self.path)
        self._workbook.close()
        self._is_closed = True

    def _ensure_open(self) -> None:
        if self._is_closed:
            raise RuntimeError("Excel はすでに閉じています。with ブロック内で操作してください。")

    def _mark_dirty(self) -> None:
        self._ensure_open()
        self._is_dirty = True

    def _is_pristine_workbook(self) -> bool:
        worksheet = cast(Worksheet, self._workbook.active)
        return len(self._workbook.worksheets) == 1 and worksheet["A1"].value is None


class Sheet:
    """Excel シートのデータ領域または表示領域を操作する。"""

    def __init__(self, excel: Excel, worksheet: Worksheet, data_prefix: str) -> None:
        self._excel = excel
        self._worksheet = worksheet
        self._data_prefix = data_prefix

    @property
    def is_data_sheet(self) -> bool:
        """プレフィックス付きのデータシートか返す。"""
        return self._worksheet.title.startswith(self._data_prefix)

    def table(self) -> "ExcelTable":
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
        return _blank(self._worksheet[cell].value)

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
        has_different_size = len(cells) != len(values) or any(
            len(row) != len(value_row) for row, value_row in zip(cells, values, strict=False)
        )
        if has_different_size:
            raise ValueError("指定範囲と values の行数・列数が一致しません。")
        for cell_row, value_row in zip(cells, values, strict=True):
            for cell, value in zip(cell_row, value_row, strict=True):
                cell.value = value
        self._excel._mark_dirty()

    def read_range(self, cell_range: str) -> list[dict[str, Value]]:
        """指定範囲の先頭行を見出しとして辞書のリストで読む。"""
        self._ensure_display_sheet("read_range")
        rows = [[_blank(cell.value) for cell in row] for row in self._worksheet[cell_range]]
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
        """行を非表示にする。"""
        self._set_row_hidden(row, True)

    def show_row(self, row: int) -> None:
        """行を表示する。"""
        self._set_row_hidden(row, False)

    def hide_column(self, col: str) -> None:
        """列を非表示にする。"""
        self._set_column_hidden(col, True)

    def show_column(self, col: str) -> None:
        """列を表示する。"""
        self._set_column_hidden(col, False)

    def insert_row(self, row: int) -> None:
        """行を挿入する。"""
        self._ensure_display_sheet("insert_row")
        self._worksheet.insert_rows(row)
        self._excel._mark_dirty()

    def delete_row(self, row: int) -> None:
        """行を削除する。"""
        self._ensure_display_sheet("delete_row")
        self._worksheet.delete_rows(row)
        self._excel._mark_dirty()

    def insert_column(self, col: str) -> None:
        """列を挿入する。"""
        self._ensure_display_sheet("insert_column")
        self._worksheet.insert_cols(column_index_from_string(col))
        self._excel._mark_dirty()

    def delete_column(self, col: str) -> None:
        """列を削除する。"""
        self._ensure_display_sheet("delete_column")
        self._worksheet.delete_cols(column_index_from_string(col))
        self._excel._mark_dirty()

    def format(self, cell: str, **kwargs: Any) -> None:
        """セルのフォントと表示形式を設定する。"""
        self._ensure_display_sheet("format")
        target = self._worksheet[cell]
        font_keys = {"bold", "italic", "size", "name", "color"}
        font_values = {key: value for key, value in kwargs.items() if key in font_keys}
        unknown = set(kwargs) - font_keys - {"number_format"}
        if unknown:
            raise TypeError(f"format() で使用できない引数です: {sorted(unknown)}")
        if font_values:
            font = copy(target.font)
            for key, value in font_values.items():
                setattr(font, key, value)
            target.font = font
        if "number_format" in kwargs:
            target.number_format = str(kwargs["number_format"])
        self._excel._mark_dirty()

    def set_background(self, cell: str, color: str) -> None:
        """セルの背景色を設定する。"""
        self._ensure_display_sheet("set_background")
        self._worksheet[cell].fill = PatternFill("solid", fgColor=color.removeprefix("#"))
        self._excel._mark_dirty()

    def set_border(self, cell: str, **kwargs: Any) -> None:
        """セルの四辺へ同じ罫線を設定する。"""
        self._ensure_display_sheet("set_border")
        style: Any = str(kwargs.pop("style", "thin"))
        color = str(kwargs.pop("color", "000000")).removeprefix("#")
        if kwargs:
            raise TypeError(f"set_border() で使用できない引数です: {sorted(kwargs)}")
        side = Side(style=style, color=color)
        self._worksheet[cell].border = Border(left=side, right=side, top=side, bottom=side)
        self._excel._mark_dirty()

    def merge_cells(self, cell_range: str) -> None:
        """セル範囲を結合する。"""
        self._ensure_display_sheet("merge_cells")
        self._worksheet.merge_cells(cell_range)
        self._excel._mark_dirty()

    def unmerge_cells(self, cell_range: str) -> None:
        """セル範囲の結合を解除する。"""
        self._ensure_display_sheet("unmerge_cells")
        self._worksheet.unmerge_cells(cell_range)
        self._excel._mark_dirty()

    def freeze_panes(self, cell: str) -> None:
        """指定セルを基準にウィンドウ枠を固定する。"""
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


class ExcelTable:
    """データシート全体を1つのテーブルとして操作する。"""

    def __init__(self, excel: Excel, worksheet: Worksheet) -> None:
        self._excel = excel
        self._worksheet = worksheet

    def read(self) -> list[dict[str, Value]]:
        """データシート全体を辞書のリストで読む。"""
        self._excel._ensure_open()
        rows = list(self._worksheet.iter_rows(values_only=True))
        if not rows or all(value is None for value in rows[0]):
            return []
        last_column = max(
            (
                index
                for row in rows
                for index, value in enumerate(row, start=1)
                if value is not None
            ),
            default=0,
        )
        headers = list(rows[0][:last_column])
        empty_columns = [index for index, header in enumerate(headers, start=1) if header is None]
        if empty_columns:
            raise EmptyHeaderCellError(empty_columns)
        duplicate_headers = [
            header for header in dict.fromkeys(headers) if headers.count(header) > 1
        ]
        if duplicate_headers:
            raise DuplicateHeaderCellError(duplicate_headers)
        return [
            {
                str(header): _blank(value)
                for header, value in zip(headers, row[:last_column], strict=True)
            }
            for row in rows[1:]
            if any(value is not None for value in row[:last_column])
        ]

    def replace(self, rows: list[dict[str, Value]]) -> None:
        """データシート全体を置き換える。"""
        self._excel._ensure_open()
        self._worksheet.delete_rows(1, self._worksheet.max_row)
        if rows:
            headers = list(rows[0])
            for column, header in enumerate(headers, start=1):
                self._worksheet.cell(row=1, column=column, value=header)
            for row_number, row in enumerate(rows, start=2):
                for column, header in enumerate(headers, start=1):
                    self._worksheet.cell(row=row_number, column=column, value=row.get(header, ""))
        self._excel._mark_dirty()

    def count(self) -> int:
        """データ行数を返す。"""
        return len(self.read())


def _blank(value: Any) -> Value:
    return "" if value is None else value
