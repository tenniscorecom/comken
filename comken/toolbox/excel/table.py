"""comken/toolbox/excel/table.py — Excel データシートを操作する。"""

from datetime import datetime
from typing import TYPE_CHECKING, TypeAlias

from openpyxl.utils.cell import range_boundaries
from openpyxl.worksheet.worksheet import Worksheet

from comken.core.table.model import Table
from comken.exceptions import (
    DuplicateHeaderCellError,
    EmptyExcelTableError,
    EmptyHeaderCellError,
    InvalidTableInputError,
    InvalidTableOperationError,
    TableFormulaOverwriteError,
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

    def read(self, *, force_com: bool = False) -> Table:
        """Excelテーブルの実際の定義範囲だけを読み、値を返す。

        シートの使用範囲ではなく Excel が保持する ``ref`` を使うため、表の外に
        ある無関係なセルを現在の Table に混ぜません。数式の計算結果が
        保存されていない場合だけ内部でCOMへ切り替えます。``force_com=True``
        はキャッシュを信頼できないブックをExcel実機で強制再計算します。
        """
        self._excel._ensure_open()
        if self._name is None:
            table_names = list(self._worksheet.tables)
            if len(table_names) != 1:
                raise InvalidTableOperationError("対象テーブルを一意に決められません。")
            self._name = table_names[0]
        excel_table = self._worksheet.tables[self._name]
        min_col, min_row, max_col, max_row = _table_boundaries(excel_table.ref)
        formula_cells = [
            cell
            for row in self._worksheet.iter_rows(
                min_row=min_row + 1, max_row=max_row, min_col=min_col, max_col=max_col
            )
            for cell in row
            if isinstance(cell.value, str) and cell.value.startswith("=")
        ]
        if force_com or (formula_cells and self._excel._is_dirty):
            rows = self._excel._read_range_with_com(
                self._worksheet.title, min_col, min_row, max_col, max_row
            )
        elif formula_cells:
            rows, needs_com = self._excel._cached_range(
                self._worksheet.title, min_col, min_row, max_col, max_row
            )
            if needs_com:
                rows = self._excel._read_range_with_com(
                    self._worksheet.title, min_col, min_row, max_col, max_row
                )
        else:
            # 数式がない表は現在のメモリ上の値を読む。新規ブックはまだ
            # 作業ファイルが無いため、毎回キャッシュ用ブックを開いてはいけない。
            rows = [
                tuple(cell.value for cell in row)
                for row in self._worksheet.iter_rows(
                    min_row=min_row, max_row=max_row, min_col=min_col, max_col=max_col
                )
            ]
        if not rows:
            raise EmptyExcelTableError(
                self._worksheet.title,
                "テーブル範囲を読み取れませんでした",
            )
        # ref が定義する列数をそのまま使う。末尾の空見出しを切り捨てると、
        # テーブル定義の壊れを見逃し、後ろの列データを失うため。
        headers = list(rows[0])
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
                for header, value in zip(headers, row, strict=True)
            }
            for row in rows[1:]
            if any(value is not None for value in row)
        ]
        return Table([str(header) for header in headers], result, types=self._excel._types)

    def replace(
        self,
        rows: list[dict[str, Value]] | Table,
        *,
        allow_formula_overwrite: bool = False,
    ) -> None:
        """データシート全体を置き換える。

        既存データ部に人が入れた数式があると、既定では ``TableFormulaOverwriteError``
        で止める。数式を値で潰すと依存セルや集計式が壊れたことに遅れて気づくため。
        意図的に上書きしてよいときだけ ``allow_formula_overwrite=True`` を渡す。
        """
        self._excel._ensure_writable("replace")
        if self._name is None:
            names = list(self._worksheet.tables)
            if len(names) != 1:
                raise InvalidTableOperationError("書き込み対象テーブルを一意に決められません。")
            self._name = names[0]
        excel_table = self._worksheet.tables[self._name]
        min_col, min_row, max_col, max_row = _table_boundaries(excel_table.ref)
        if not allow_formula_overwrite:
            # データ部（min_row+1 から max_row）の人が入れた数式を検出する。
            # 見出し行は通常文字列なので対象外。
            formula_locations = [
                cell.coordinate
                for row in self._worksheet.iter_rows(
                    min_row=min_row + 1,
                    max_row=max_row,
                    min_col=min_col,
                    max_col=max_col,
                )
                for cell in row
                if isinstance(cell.value, str) and cell.value.startswith("=")
            ]
            if formula_locations:
                raise TableFormulaOverwriteError(self._name, formula_locations)
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
        # ref を再パースせず上の _table_boundaries() の結果を使い回す。openpyxl の
        # range_boundaries() は ``tuple[int | None, ...]`` を返すため、ここでは
        # ヘルパー側で ``int`` へ正規化した値を直接参照する。
        new_max_row = min_row + max(len(rows), 1)
        last_cell = self._worksheet.cell(
            new_max_row,
            min_col + len(headers) - 1,
        ).coordinate
        excel_table.ref = f"{self._worksheet.cell(min_row, min_col).coordinate}:{last_cell}"
        self._excel._mark_dirty()

    def append(
        self,
        rows: list[dict[str, Value]] | dict[str, Value] | Table,
        *,
        allow_formula_overwrite: bool = False,
    ) -> None:
        """Table、1行、または行リストを既存テーブルの末尾へ追加する。"""
        self._excel._ensure_writable("append")
        current = self.read()
        if isinstance(rows, Table):
            additions = rows.read()
        elif isinstance(rows, dict):
            additions = [rows]
        elif isinstance(rows, list):
            additions = rows
        else:
            raise InvalidTableInputError(
                "ExcelTable の追記には Table、1行、または行リストを指定してください。"
            )
        current.append(additions)
        self.replace(current, allow_formula_overwrite=allow_formula_overwrite)

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


def _table_boundaries(excel_table_ref: str) -> tuple[int, int, int, int]:
    """Excel テーブル ref を int 4 要素 ``(min_col, min_row, max_col, max_row)`` へ正規化する。

    openpyxl の ``range_boundaries()`` は返り値を ``tuple[int | None, ...]`` と推論するが、
    Excel テーブル ref は validated 済みの範囲なので通常 ``None`` にはならない。
    呼び出し側で None を意識せずに済むよう、ここで ``int`` へ揃えて返す。

    もし ``None`` が現れた場合のフォールバックは 0 とする。空テーブルを置換した結果として
    ref の各値が 0 に丸まっても、その直後の ``cell(...)`` 呼び出しが「先頭セル」として
    動くので、利用者に見える不整合は出ない（発注元の判断）。
    """
    min_col, min_row, max_col, max_row = range_boundaries(excel_table_ref)
    return (
        0 if min_col is None else min_col,
        0 if min_row is None else min_row,
        0 if max_col is None else max_col,
        0 if max_row is None else max_row,
    )
