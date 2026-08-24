"""comken/toolbox/excel/sheet.py — Excel シートを操作する。"""

from copy import copy
from typing import TYPE_CHECKING, Any, Literal

from openpyxl.styles import Border, PatternFill, Side
from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.utils.cell import coordinate_from_string
from openpyxl.worksheet.table import Table as OpenPyXLTable
from openpyxl.worksheet.table import TableStyleInfo
from openpyxl.worksheet.worksheet import Worksheet

from comken.core.table.model import Table
from comken.exceptions import (
    DataSheetAccessError,
    InvalidTableInputError,
    InvalidTableOperationError,
    TableAlreadyExistsError,
    TableNotFoundError,
)
from comken.toolbox.excel.table import ExcelTable

if TYPE_CHECKING:
    from comken.core.table.model import Table
    from comken.toolbox.excel.workbook import Excel

# openpyxl の Side が受け付ける境界線のスタイル。
# 値の一覧は openpyxl.styles.Side.style の NoneSet に従う。
BorderStyle = Literal[
    "dashDot",
    "dashDotDot",
    "dashed",
    "dotted",
    "double",
    "hair",
    "medium",
    "mediumDashDot",
    "mediumDashDotDot",
    "mediumDashed",
    "slantDashDot",
    "thick",
    "thin",
]


class Sheet:
    """Excel シートのデータ領域または表示領域を操作する。"""

    PY_TABLE_PREFIX = "PY_T_"

    def __init__(self, excel: "Excel", worksheet: Worksheet) -> None:
        self._excel = excel
        self._worksheet = worksheet

    @property
    def is_data_sheet(self) -> bool:
        """プレフィックス付きのデータシートか返す。"""
        return self._excel._is_data_sheet_name(self._worksheet.title)

    def table(self, name: str | None = None) -> ExcelTable:
        """データシート全体を扱うテーブルを返す。"""
        if not self.is_data_sheet:
            raise DataSheetAccessError(self._worksheet.title, "table")
        table_names = list(self._worksheet.tables)
        if name is not None:
            name = self._with_table_prefix(name)
            if name not in table_names:
                raise TableNotFoundError(name, table_names)
        if name is None and len(table_names) > 1:
            raise InvalidTableOperationError(
                "1シートに複数テーブルがあります。table(name)で指定してください。"
            )
        return ExcelTable(self._excel, self._worksheet, name)

    def create_table(self, name: str, table: "Table", start_cell: str = "A1") -> ExcelTable:
        """Python管理用の実テーブルを新規作成する。

        ``start_cell`` は見出しの左上セルです。作成直後の Table はメモリ上の
        現在値で、Excel ファイルへの保存は Excel の save/with 契約で後から行います。
        """
        if not self.is_data_sheet:
            raise DataSheetAccessError(self._worksheet.title, "create_table")
        full_name = self._with_table_prefix(name)
        if any(full_name in worksheet.tables for worksheet in self._excel._workbook.worksheets):
            raise TableAlreadyExistsError(full_name)
        if not isinstance(table, Table):
            raise InvalidTableInputError("create_table には Table を指定してください。")
        if not table.columns:
            raise InvalidTableInputError("列がないTableはExcelテーブルにできません。")
        try:
            start_column, start_row = coordinate_from_string(start_cell)
            start_column_number = column_index_from_string(start_column)
        except (TypeError, ValueError):
            raise InvalidTableInputError(f"start_cell が不正です: {start_cell!r}") from None
        for column, header in enumerate(table.columns, start_column_number):
            self._worksheet.cell(start_row, column, header)
        for row_number, row in enumerate(table.rows, start_row + 1):
            for column, header in enumerate(table.columns, 1):
                self._worksheet.cell(
                    row_number,
                    start_column_number + column - 1,
                    row.get(header, ""),
                )
        end_row = max(start_row + len(table.rows), start_row + 1)
        end_column = start_column_number + len(table.columns) - 1
        # Excel の実テーブル範囲は、無関係なセルではなく見出し・データから計算します。
        ref = f"{start_cell.upper()}:{get_column_letter(end_column)}{end_row}"
        excel_table = OpenPyXLTable(displayName=full_name, ref=ref)
        excel_table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )
        self._worksheet.add_table(excel_table)
        self._excel._mark_dirty()
        return ExcelTable(self._excel, self._worksheet, full_name)

    @staticmethod
    def _with_table_prefix(name: str) -> str:
        """短いテーブル名に、Python管理用の ``PY_T_`` を補う。"""
        return name if name.startswith(Sheet.PY_TABLE_PREFIX) else f"{Sheet.PY_TABLE_PREFIX}{name}"

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
        """指定した行を非表示にする。

        行の表示設定はデータ表の内容ではなく画面レイアウトなので、データシート
        ではなく表示シートに限定している。
        """
        self._set_row_hidden(row, True)

    def show_row(self, row: int) -> None:
        """指定した行の非表示を解除する。"""
        self._set_row_hidden(row, False)

    def hide_column(self, col: str) -> None:
        """指定した列を非表示にする。"""
        self._set_column_hidden(col, True)

    def show_column(self, col: str) -> None:
        """指定した列の非表示を解除する。"""
        self._set_column_hidden(col, False)

    def insert_row(self, row: int) -> None:
        """指定位置に表示用の行を挿入する。"""
        self._ensure_display_sheet("insert_row")
        self._worksheet.insert_rows(row)
        self._excel._mark_dirty()

    def delete_row(self, row: int) -> None:
        """指定位置の表示用の行を削除する。"""
        self._ensure_display_sheet("delete_row")
        self._worksheet.delete_rows(row)
        self._excel._mark_dirty()

    def insert_column(self, col: str) -> None:
        """指定位置に表示用の列を挿入する。"""
        self._ensure_display_sheet("insert_column")
        self._worksheet.insert_cols(column_index_from_string(col))
        self._excel._mark_dirty()

    def delete_column(self, col: str) -> None:
        """指定位置の表示用の列を削除する。"""
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
        """セルの背景色を設定する。"""
        self._ensure_display_sheet("set_background")
        self._worksheet[cell].fill = PatternFill("solid", fgColor=color.removeprefix("#"))
        self._excel._mark_dirty()

    def set_border(
        self,
        cell: str,
        *,
        style: BorderStyle = "thin",
        color: str = "000000",
    ) -> None:
        """セルの四辺に同じ境界線を設定する。

        よく使う ``style``: ``"thin"`` / ``"medium"`` / ``"thick"`` /
        ``"dashed"`` / ``"double"``。全種類は ``BorderStyle`` 型を参照。

        Args:
            cell: 対象のセル参照 (例: ``"A1"``)。
            style: 線の種類。 ``BorderStyle`` で定義したいずれかの値。
            color: 16進数 6 桁の色 (``#`` 付きでも可)。既定は ``"000000"``。

        Raises:
            ValueError: ``style`` が ``BorderStyle`` のいずれにも該当しない
                (openpyxl の検証による)。
        """
        self._ensure_display_sheet("set_border")
        side = Side(style=style, color=color.removeprefix("#"))
        self._worksheet[cell].border = Border(left=side, right=side, top=side, bottom=side)
        self._excel._mark_dirty()

    def merge_cells(self, cell_range: str) -> None:
        """指定範囲のセルを結合する。"""
        self._ensure_display_sheet("merge_cells")
        self._worksheet.merge_cells(cell_range)
        self._excel._mark_dirty()

    def unmerge_cells(self, cell_range: str) -> None:
        """指定範囲のセル結合を解除する。"""
        self._ensure_display_sheet("unmerge_cells")
        self._worksheet.unmerge_cells(cell_range)
        self._excel._mark_dirty()

    def freeze_panes(self, cell: str) -> None:
        """指定セルより上・左の領域を固定表示する。"""
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
