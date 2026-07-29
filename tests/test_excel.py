"""
ExcelReader / ExcelWriter クラスのテスト。

実行方法:
    リポジトリのルートで python -m pytest tests/ -v
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from openpyxl import Workbook, load_workbook
from pywintypes import com_error

import comken.excel
from comken.excel import ExcelReader, ExcelWriter
from comken.exceptions import (
    ExcelError,
    ExcelFormulaError,
    InvalidTableNameError,
    LastSheetDeletionError,
    OriginalLibsError,
    SheetAlreadyExistsError,
    SheetNotFoundError,
    TableAlreadyExistsError,
    TableNotFoundError,
    UnsupportedFileSuffixError,
)
from comken.utils.data import col_to_num
from comken.windows.handler import ExcelComHandler


@pytest.fixture
def excel_with_header(tmp_path):
    """1行目がヘッダーの Excel ファイルを作成して返す。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["注文番号", "金額", "担当者"])
    ws.append(["A001", 1000, "山田"])
    ws.append(["A002", 2000, "佐藤"])
    path = tmp_path / "data.xlsx"
    wb.save(path)
    return path


@pytest.fixture
def excel_no_header(tmp_path):
    """ヘッダー行なし（全行データ）の Excel ファイルを作成して返す。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["A001", 1000, "山田"])
    ws.append(["A002", 2000, "佐藤"])
    path = tmp_path / "no_header.xlsx"
    wb.save(path)
    return path


@pytest.fixture
def excel_header_row2(tmp_path):
    """2行目がヘッダーの Excel ファイルを作成して返す。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["（この行は無視）", None, None])
    ws.append(["注文番号", "金額", "担当者"])
    ws.append(["A001", 1000, "山田"])
    path = tmp_path / "header_row2.xlsx"
    wb.save(path)
    return path


class TestExcelReader:
    def test_path_is_path(self, excel_with_header: Path) -> None:
        with ExcelReader(str(excel_with_header)) as reader:
            assert reader.path == excel_with_header
            assert isinstance(reader.path, Path)

    def test_rejects_non_excel_suffix(self, tmp_path: Path) -> None:
        with pytest.raises(UnsupportedFileSuffixError):
            ExcelReader(tmp_path / "data.csv")

    def test_reads_value_written_by_writer(self, tmp_path: Path) -> None:
        path = tmp_path / "book.xlsx"
        with ExcelWriter.create(path) as writer:
            sheet = writer.sheet("Sheet1")
            sheet.write_cell(row=1, col=1, value="見出し")
            sheet.write_cell(row=2, col=1, value="値")
            writer.save()

        with ExcelReader(path) as reader:
            assert reader.read_rows("Sheet1") == [("値",)]
            assert reader._wb.read_only is True
            assert not hasattr(reader, "write_cell")


class TestExcelWriterColumn:
    @pytest.mark.parametrize("col", ["A", "AA", 27])
    def test_write_cell_accepts_column_letter_or_number(self, tmp_path, col):
        with ExcelWriter.create(tmp_path / "book.xlsx") as writer:
            writer.sheet("Sheet1").write_cell(row=2, col=col, value="値")
            expected_col = 1 if col == "A" else 27
            assert writer._wb["Sheet1"].cell(2, expected_col).value == "値"

    @pytest.mark.parametrize("col", ["A", "AA", 27])
    def test_format_methods_accept_column_letter_or_number(self, tmp_path, col):
        with ExcelWriter.create(tmp_path / "book.xlsx") as writer:
            sheet = writer.sheet("Sheet1")
            sheet.set_fill(2, col, "FFFF00")
            sheet.set_column_width(col, 20)
            sheet.set_number_format(2, col, "#,##0")
            sheet.set_bold(2, col)
            expected_col = 1 if col == "A" else 27
            cell = writer._wb["Sheet1"].cell(2, expected_col)
            assert cell.fill.fgColor.rgb == "00FFFF00"
            assert (
                writer._wb["Sheet1"].column_dimensions["A" if expected_col == 1 else "AA"].width
                == 20
            )
            assert cell.number_format == "#,##0"
            assert cell.font.bold is True


class TestExcelWriterSheetOperations:
    def test_add_sheet_returns_writable_sheet(self, tmp_path: Path) -> None:
        with ExcelWriter.create(tmp_path / "book.xlsx") as writer:
            sheet = writer.add_sheet("集計")
            sheet.write_table([{"注文番号": "A001", "金額": 1000}])

            assert writer._wb.sheetnames == ["Sheet1", "集計"]
            assert writer._wb["集計"]["A2"].value == "A001"

    def test_add_sheet_inserts_at_index(self, tmp_path: Path) -> None:
        with ExcelWriter.create(tmp_path / "book.xlsx") as writer:
            writer.add_sheet("末尾")
            writer.add_sheet("先頭", index=0)

            assert writer._wb.sheetnames == ["先頭", "Sheet1", "末尾"]

    def test_rejects_duplicate_sheet_name(self, tmp_path: Path) -> None:
        with (
            ExcelWriter.create(tmp_path / "book.xlsx") as writer,
            pytest.raises(SheetAlreadyExistsError, match="別のシート名"),
        ):
            writer.add_sheet("Sheet1")

    def test_renames_and_deletes_sheet(self, tmp_path: Path) -> None:
        with ExcelWriter.create(tmp_path / "book.xlsx") as writer:
            writer.add_sheet("作業用")
            writer.rename_sheet("Sheet1", "元データ")
            writer.delete_sheet("作業用")

            assert writer._wb.sheetnames == ["元データ"]

    @pytest.mark.parametrize("operation", ["rename", "delete"])
    def test_missing_sheet_raises_sheet_not_found(self, tmp_path: Path, operation: str) -> None:
        with (
            ExcelWriter.create(tmp_path / "book.xlsx") as writer,
            pytest.raises(SheetNotFoundError, match="Sheet1"),
        ):
            if operation == "rename":
                writer.rename_sheet("なし", "新名称")
            else:
                writer.delete_sheet("なし")

    def test_rejects_deleting_last_sheet(self, tmp_path: Path) -> None:
        with (
            ExcelWriter.create(tmp_path / "book.xlsx") as writer,
            pytest.raises(LastSheetDeletionError, match="先に別のシート"),
        ):
            writer.delete_sheet("Sheet1")


class TestExcelWriterInvalidColumn:
    @pytest.mark.parametrize("col", ["", "A1", "あ"])
    def test_rejects_invalid_column_letter_with_guidance(self, tmp_path, col):
        with (
            ExcelWriter.create(tmp_path / "book.xlsx") as writer,
            pytest.raises(OriginalLibsError, match="例: 1"),
        ):
            writer.sheet("Sheet1").write_cell(row=2, col=col, value="値")


class TestExcelComHandlerColumn:
    @pytest.mark.parametrize(("col", "expected"), [("A", 1), ("AA", 27), (27, 27)])
    def test_read_and_write_accept_column_letter_or_number(self, col, expected):
        handler = ExcelComHandler.__new__(ExcelComHandler)
        sheet = MagicMock()
        sheet.Cells.return_value.Value = "読取値"
        handler._sheet = MagicMock(return_value=sheet)

        assert handler.read_cell("Sheet1", 2, col) == "読取値"
        handler.write_cell("Sheet1", 2, col, "書込値")

        assert sheet.Cells.call_args_list == [((2, expected),), ((2, expected),)]
        assert sheet.Cells.return_value.Value == "書込値"


class TestExcelComHandlerRecalculate:
    @staticmethod
    def _handler(*sheets: MagicMock) -> ExcelComHandler:
        handler = ExcelComHandler.__new__(ExcelComHandler)
        handler._path = Path("book.xlsx")
        handler._excel = MagicMock()
        handler._wb = SimpleNamespace(Worksheets=sheets)
        return handler

    @staticmethod
    def _sheet(name: str, *errors: tuple[str, str]) -> MagicMock:
        sheet = MagicMock()
        sheet.Name = name
        sheet.UsedRange.SpecialCells.return_value.Cells = [
            SimpleNamespace(Address=address, Text=error) for address, error in errors
        ]
        return sheet

    def test_recalculates_and_uses_special_cells(self) -> None:
        sheet = self._sheet("Sheet1")
        handler = self._handler(sheet)

        handler.recalculate()

        handler._excel.CalculateFull.assert_called_once_with()
        sheet.UsedRange.SpecialCells.assert_called_once_with(-4123, 16)

    def test_ranges_use_only_the_requested_range(self) -> None:
        sheet = self._sheet("Sheet1", ("$Z$99", "#REF!"))
        requested = MagicMock()
        requested.SpecialCells.side_effect = com_error()
        sheet.Range.return_value = requested
        handler = self._handler(sheet)

        handler.recalculate(ranges={"Sheet1": "E1:E2"})

        sheet.Range.assert_called_once_with("E1:E2")
        requested.SpecialCells.assert_called_once_with(-4123, 16)
        sheet.UsedRange.SpecialCells.assert_not_called()

    def test_ranges_reject_unknown_sheet(self) -> None:
        handler = self._handler(self._sheet("Sheet1"))

        with pytest.raises(SheetNotFoundError):
            handler.recalculate(ranges={"Missing": "A1:A1"})

    def test_default_errors_include_location_and_error(self) -> None:
        sheet = self._sheet("集計", ("$E$1", "#NAME?"), ("$F$2", "#REF!"))
        handler = self._handler(sheet)

        with pytest.raises(ExcelFormulaError) as exc_info:
            handler.recalculate()

        message = str(exc_info.value)
        assert "集計!$E$1" in message
        assert "#NAME?" in message
        assert "集計!$F$2" in message
        assert "#REF!" in message
        assert "テーブル名" in message

    def test_default_ignores_na(self) -> None:
        handler = self._handler(self._sheet("Sheet1", ("$A$1", "#N/A")))
        handler.recalculate()

    def test_error_values_can_be_changed(self) -> None:
        handler = self._handler(self._sheet("Sheet1", ("$A$1", "#N/A")))

        with pytest.raises(ExcelFormulaError, match="#N/A"):
            handler.recalculate(error_values=("#N/A",))

    def test_many_errors_are_truncated(self) -> None:
        errors = tuple((f"$A${index}", "#REF!") for index in range(1, 13))
        handler = self._handler(self._sheet("Sheet1", *errors))

        with pytest.raises(ExcelFormulaError) as exc_info:
            handler.recalculate()

        message = str(exc_info.value)
        assert "$A$10" in message
        assert "$A$11" not in message
        assert "他 2 件" in message

    def test_special_cells_no_match_is_success(self) -> None:
        sheet = self._sheet("Sheet1")
        sheet.UsedRange.SpecialCells.side_effect = com_error()
        handler = self._handler(sheet)

        handler.recalculate()


class TestExcelComHandlerTransferByKey:
    def test_reads_and_writes_ranges_in_bulk(self) -> None:
        source = (
            (1001.0, "旧顧客", "旧金額"),
            (1002.0, "旧顧客続き", "旧金額続き"),
            (None, "数式を想定した未一致値", 0),
            ("A002", "旧顧客2", "旧金額2"),
        )
        written: dict[tuple[int, int, int], tuple] = {}

        class FakeRange:
            def __init__(self, start: tuple[int, int], end: tuple[int, int]) -> None:
                self.start = start
                self.end = end

            @property
            def Value(self):
                return source

            @Value.setter
            def Value(self, value) -> None:
                written[(self.start[0], self.end[0], self.start[1])] = value

        sheet = MagicMock()
        sheet.Cells.side_effect = lambda row, col: (row, col)
        sheet.Range.side_effect = lambda start, end: FakeRange(start, end)
        sheet.UsedRange = SimpleNamespace(
            Row=1,
            Column=1,
            Rows=SimpleNamespace(Count=5),
            Columns=SimpleNamespace(Count=3),
        )

        handler = ExcelComHandler.__new__(ExcelComHandler)
        handler._sheet = MagicMock(return_value=sheet)
        handler.used_last_row = MagicMock(return_value=5)

        matched = handler.transfer_by_key(
            "Sheet1",
            key_col="A",
            lookup={
                "1001": {"顧客名": "株式会社A", "金額": 1000},
                "1002": {"顧客名": "株式会社C", "金額": 1500},
                "A002": {"顧客名": "株式会社B", "金額": 2000},
            },
            column_mapping={"B": "顧客名", "C": "金額"},
        )

        assert matched == 3
        assert written[(2, 3, 2)] == (("株式会社A",), ("株式会社C",))
        assert written[(5, 5, 2)] == (("株式会社B",),)
        assert written[(2, 3, 3)] == ((1000,), (1500,))
        assert written[(5, 5, 3)] == ((2000,),)
        assert not any(start == 4 for start, _, _ in written)
        assert sheet.Range.call_count == 5

    def test_write_error_identifies_row(self) -> None:
        source = ((1001.0,), (1002.0,))

        class FailingRange:
            def __init__(self, start: tuple[int, int], end: tuple[int, int]) -> None:
                self.start = start
                self.end = end

            @property
            def Value(self):
                return source

            @Value.setter
            def Value(self, value) -> None:
                if self.start[0] != self.end[0] or self.start[0] == 3:
                    raise TypeError("書き込み不可")

        sheet = MagicMock()
        sheet.Cells.side_effect = lambda row, col: (row, col)
        sheet.Range.side_effect = lambda start, end: FailingRange(start, end)
        sheet.UsedRange = SimpleNamespace(
            Row=1,
            Column=1,
            Rows=SimpleNamespace(Count=3),
            Columns=SimpleNamespace(Count=1),
        )
        handler = ExcelComHandler.__new__(ExcelComHandler)
        handler._sheet = MagicMock(return_value=sheet)
        handler.used_last_row = MagicMock(return_value=3)

        with pytest.raises(ExcelError, match="3行目"):
            handler.transfer_by_key(
                "Sheet1",
                key_col="A",
                lookup={"1001": {"値": "A"}, "1002": {"値": "B"}},
                column_mapping={"B": "値"},
            )


class TestOpen:
    def test_missing_file_raises_excel_error(self, tmp_path):
        """存在しないファイルは素の FileNotFoundError ではなく ExcelError になる。"""
        with pytest.raises(ExcelError, match="見つかりません"):
            ExcelReader(tmp_path / "no_such.xlsx")


class TestReadRowsAsDicts:
    """read_rows_as_dicts() の基本動作テスト。"""

    def test_reads_all_rows(self, excel_with_header):
        """1行目ヘッダーの場合に全データ行を辞書で返すことを確認する。"""
        with ExcelReader(excel_with_header) as f:
            rows = f.read_rows_as_dicts("Sheet1")
        assert len(rows) == 2
        assert rows[0] == {"注文番号": "A001", "金額": 1000, "担当者": "山田"}

    def test_header_row_parameter(self, excel_header_row2):
        """header_row=2 の場合に2行目をヘッダーとして読むことを確認する。"""
        with ExcelReader(excel_header_row2) as f:
            rows = f.read_rows_as_dicts("Sheet1", header_row=2)
        assert len(rows) == 1
        assert rows[0]["注文番号"] == "A001"

    def test_empty_sheet_returns_empty_list(self, tmp_path):
        """空のシートは空リストを返すことを確認する。"""
        wb = Workbook()
        wb.active.title = "Sheet1"
        path = tmp_path / "empty.xlsx"
        wb.save(path)
        with ExcelReader(path) as f:
            rows = f.read_rows_as_dicts("Sheet1")
        assert rows == []

    def test_raises_on_missing_sheet(self, excel_with_header):
        """存在しないシートを指定すると SheetNotFoundError になることを確認する。"""
        with ExcelReader(excel_with_header) as f, pytest.raises(SheetNotFoundError):
            f.read_rows_as_dicts("存在しないシート")

    def test_raises_on_none_header_cell(self, tmp_path):
        """ヘッダー行に空のセルがある場合は ExcelError になることを確認する。"""
        wb = Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        ws.append(["注文番号", None, "担当者"])
        ws.append(["A001", 1000, "山田"])
        path = tmp_path / "none_header.xlsx"
        wb.save(path)
        with ExcelReader(path) as f, pytest.raises(ExcelError, match="空のセル"):
            f.read_rows_as_dicts("Sheet1")


class TestReadRowsAsDictsWithHeaders:
    """ExcelReader(path, headers=...) のテスト（ヘッダー行なしファイル）。"""

    def test_reads_headerless_file(self, excel_no_header):
        """__init__ で headers を指定すると全行をデータとして読めることを確認する。"""
        with ExcelReader(excel_no_header, headers=["注文番号", "金額", "担当者"]) as f:
            rows = f.read_rows_as_dicts("Sheet1")
        assert len(rows) == 2
        assert rows[0] == {"注文番号": "A001", "金額": 1000, "担当者": "山田"}
        assert rows[1]["注文番号"] == "A002"

    def test_headers_overrides_file_headers(self, excel_with_header):
        """__init__ で headers 指定時はファイルの1行目もデータとして読むことを確認する。

        （ヘッダーありファイルに headers を渡すと、ヘッダー行もデータになる）
        """
        with ExcelReader(excel_with_header, headers=["C1", "C2", "C3"]) as f:
            rows = f.read_rows_as_dicts("Sheet1")
        assert len(rows) == 3  # ヘッダー行を含む全3行
        assert rows[0] == {"C1": "注文番号", "C2": "金額", "C3": "担当者"}

    def test_headers_applies_to_all_sheets(self, tmp_path):
        """__init__ で headers を指定すると全シートに適用されることを確認する。"""
        wb = Workbook()
        ws1 = wb.active
        ws1.title = "Sheet1"
        ws1.append(["A001", 1000])
        ws2 = wb.create_sheet("Sheet2")
        ws2.append(["B001", 2000])
        path = tmp_path / "multi.xlsx"
        wb.save(path)

        with ExcelReader(path, headers=["注文番号", "金額"]) as f:
            rows1 = f.read_rows_as_dicts("Sheet1")
            rows2 = f.read_rows_as_dicts("Sheet2")
        assert rows1[0]["注文番号"] == "A001"
        assert rows2[0]["注文番号"] == "B001"

    def test_headers_too_few_raises(self, excel_no_header):
        """headers の列数がシートの列数より少ないとエラーになることを確認する。

        （zip が黙って列を落とすとデータ欠損に気づけないため）
        """
        with (
            ExcelReader(excel_no_header, headers=["注文番号", "金額"]) as f,  # 実際は3列
            pytest.raises(ExcelError, match="列数"),
        ):
            f.read_rows_as_dicts("Sheet1")

    def test_headers_with_empty_sheet_returns_empty(self, tmp_path):
        """headers 指定でも空シートは空リストを返すことを確認する（偽の1行を返さない）。"""
        wb = Workbook()
        wb.active.title = "Sheet1"
        path = tmp_path / "empty.xlsx"
        wb.save(path)

        with ExcelReader(path, headers=["注文番号", "金額"]) as f:
            rows = f.read_rows_as_dicts("Sheet1")
        assert rows == []

    def test_headers_skips_blank_rows(self, tmp_path):
        """全セルが空の行は結果に含まれないことを確認する。"""
        wb = Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        ws.append(["A001", 1000])
        ws.append([None, None])  # 空行
        ws.append(["A002", 2000])
        path = tmp_path / "blank_row.xlsx"
        wb.save(path)

        with ExcelReader(path, headers=["注文番号", "金額"]) as f:
            rows = f.read_rows_as_dicts("Sheet1")
        assert len(rows) == 2
        assert rows[1]["注文番号"] == "A002"


class TestTransferByKey:
    """Sheet.transfer_by_key（openpyxl 版のキー突合転記）のテスト。"""

    @pytest.fixture
    def transfer_excel(self, tmp_path):
        """転記先の Excel（キー列 A、転記先列 B・C）を作成して返す。"""
        wb = Workbook()
        ws = wb.active
        ws.title = "T_data"
        ws.append(["注文番号", "顧客名", "金額"])
        ws.append(["A001", None, None])
        ws.append(["A002", None, None])
        ws.append(["Z999", None, None])  # lookup に存在しないキー
        path = tmp_path / "transfer.xlsx"
        wb.save(path)
        return path

    def test_transfers_matching_rows(self, transfer_excel):
        """キーが一致した行に値が転記され、件数が返ることを確認する。"""
        lookup = {
            "A001": {"顧客名": "株式会社A", "金額": "1000"},
            "A002": {"顧客名": "株式会社B", "金額": "2000"},
        }

        with ExcelWriter(transfer_excel) as f:
            matched = f.sheet("T_data").transfer_by_key(
                key_col="A", lookup=lookup, column_mapping={"B": "顧客名", "C": "金額"}
            )
            f.save()

        assert matched == 2
        wb = load_workbook(transfer_excel)
        ws = wb["T_data"]
        assert ws.cell(row=2, column=2).value == "株式会社A"
        assert ws.cell(row=3, column=3).value == "2000"
        wb.close()

    def test_skips_missing_keys(self, transfer_excel):
        """lookup にないキーの行は転記されずスキップされることを確認する。"""
        lookup = {"A001": {"顧客名": "株式会社A"}}

        with ExcelWriter(transfer_excel) as f:
            matched = f.sheet("T_data").transfer_by_key(
                key_col="A", lookup=lookup, column_mapping={"B": "顧客名"}
            )
            f.save()

        assert matched == 1
        wb = load_workbook(transfer_excel)
        ws = wb["T_data"]
        assert ws.cell(row=4, column=2).value is None  # Z999 の行は未転記
        wb.close()

    def test_float_integer_key_matches_csv_string(self, tmp_path):
        """数値キー（1001.0）が CSV 側の文字列キー "1001" と突合できることを確認する。"""
        wb = Workbook()
        ws = wb.active
        ws.title = "T_data"
        ws.append(["注文番号", "顧客名"])
        ws.append([1001.0, None])
        path = tmp_path / "float_key.xlsx"
        wb.save(path)

        lookup = {"1001": {"顧客名": "株式会社C"}}

        with ExcelWriter(path) as f:
            matched = f.sheet("T_data").transfer_by_key(
                key_col="A", lookup=lookup, column_mapping={"B": "顧客名"}
            )
            f.save()

        assert matched == 1
        wb = load_workbook(path)
        assert wb["T_data"].cell(row=2, column=2).value == "株式会社C"
        wb.close()

    def test_key_col_accepts_column_number(self, transfer_excel):
        """key_col を列レターではなく列番号（1）で指定できることを確認する。"""
        lookup = {"A001": {"顧客名": "株式会社A"}}

        with ExcelWriter(transfer_excel) as f:
            matched = f.sheet("T_data").transfer_by_key(
                key_col=1, lookup=lookup, column_mapping={"B": "顧客名"}
            )

        assert matched == 1

    def test_raises_on_missing_sheet(self, transfer_excel):
        """存在しないシートを指定すると SheetNotFoundError になることを確認する。"""
        with ExcelWriter(transfer_excel) as f, pytest.raises(SheetNotFoundError):
            f.sheet("存在しない").transfer_by_key(key_col="A", lookup={}, column_mapping={})


class TestSheetWrapper:
    """Sheet（シート単位の高レベルラッパー）のテスト。"""

    def test_create_and_cell_access(self, tmp_path):
        """ExcelWriter.create で新規ブックを作り、セル参照で読み書きできることを確認する。"""
        path = tmp_path / "new.xlsx"
        with ExcelWriter.create(path) as f:
            s = f.sheet("Sheet1")
            s["A1"] = "タイトル"

            assert s["A1"] == "タイトル"
            f.save()

        assert path.exists()

    def test_written_ranges_include_values_but_not_formatting(self, tmp_path):
        with ExcelWriter.create(tmp_path / "ranges.xlsx") as writer:
            sheet = writer.sheet("Sheet1")
            sheet["C3"] = "value"
            sheet.write_cell(5, "E", "value")
            sheet.write_rows(7, [[1, 2]], start_col=2)
            sheet.write_table([{"first": 1, "second": 2}], start_row=10)
            sheet["A13"] = "key"
            sheet.transfer_by_key(
                key_col="A",
                lookup={"key": {"result": "ok"}},
                column_mapping={"D": "result"},
                start_row=12,
            )
            formatted = writer.add_sheet("Formatted")
            formatted.set_fill(1, "A", "FFFF00")

            assert writer.written_ranges() == {"Sheet1": "A3:E13"}

    def test_written_ranges_wrap_disjoint_cells(self, tmp_path):
        with ExcelWriter.create(tmp_path / "ranges.xlsx") as writer:
            sheet = writer.sheet("Sheet1")
            sheet["B2"] = 1
            sheet["F9"] = 2

            assert writer.written_ranges() == {"Sheet1": "B2:F9"}

    def test_transfer_by_key_expands_written_range_to_output_column(self, tmp_path):
        with ExcelWriter.create(tmp_path / "ranges.xlsx") as writer:
            sheet = writer.sheet("Sheet1")
            sheet["A2"] = "key"

            sheet.transfer_by_key(
                key_col="A",
                lookup={"key": {"result": "ok"}},
                column_mapping={"D": "result"},
            )

            assert writer.written_ranges() == {"Sheet1": "A2:D2"}

    def test_write_row_and_rows(self, tmp_path):
        """write_row / write_rows で横並びに書き込まれることを確認する。"""
        path = tmp_path / "rows.xlsx"
        with ExcelWriter.create(path) as f:
            s = f.sheet("Sheet1")
            s.write_row(1, ["日付", "金額"])
            s.write_rows(2, [["7/1", 100], ["7/2", 200]])
            f.save()

        with ExcelReader(path) as f:
            rows = f.read_rows_as_dicts("Sheet1")
            assert rows == [{"日付": "7/1", "金額": 100}, {"日付": "7/2", "金額": 200}]

    def test_append_row_on_empty_sheet_starts_at_row1(self, tmp_path):
        """空シートへの append_row は1行目から書かれることを確認する（2行目から始まらない）。"""
        with ExcelWriter.create(tmp_path / "a.xlsx") as f:
            s = f.sheet("Sheet1")
            assert s.is_empty

            s.append_row(["ヘッダー"])
            s.append_row(["データ"])

            assert s["A1"] == "ヘッダー"
            assert s["A2"] == "データ"
            assert not s.is_empty

    def test_write_table_writes_header_and_rows(self, tmp_path):
        """write_table で辞書のリストがヘッダー付きで書かれることを確認する。"""
        rows = [{"注文番号": "A001", "金額": 1000}, {"注文番号": "A002", "金額": 2000}]
        path = tmp_path / "table.xlsx"
        with ExcelWriter.create(path) as f:
            f.sheet("Sheet1").write_table(rows)
            f.save()

        with ExcelReader(path) as f:
            assert f.read_rows_as_dicts("Sheet1") == rows

    def test_write_table_respects_header_order(self, tmp_path):
        """headers 指定で列の並び順を制御できることを確認する。"""
        rows = [{"金額": 1000, "注文番号": "A001"}]
        with ExcelWriter.create(tmp_path / "t.xlsx") as f:
            s = f.sheet("Sheet1")
            s.write_table(rows, headers=["注文番号", "金額"])

            assert s["A1"] == "注文番号"
            assert s["B1"] == "金額"

    def test_auto_width_considers_japanese(self, tmp_path):
        """auto_width で全角文字が2文字ぶんとして幅計算されることを確認する。"""
        with ExcelWriter.create(tmp_path / "w.xlsx") as f:
            s = f.sheet("Sheet1")
            s["A1"] = "日本語のタイトル"  # 8文字 → 表示幅16
            s["B1"] = "abc"

            s.auto_width()

            assert s.ws.column_dimensions["A"].width >= 16
            assert s.ws.column_dimensions["B"].width == 8  # min_width

    def test_auto_width_caps_at_max(self, tmp_path):
        """長文があっても max_width を超えないことを確認する。"""
        with ExcelWriter.create(tmp_path / "w.xlsx") as f:
            s = f.sheet("Sheet1")
            s["A1"] = "あ" * 100

            s.auto_width(max_width=60)

            assert s.ws.column_dimensions["A"].width == 60

    def test_freeze_header(self, tmp_path):
        """freeze_header で1行目（指定行数）が固定されることを確認する。"""
        with ExcelWriter.create(tmp_path / "f.xlsx") as f:
            s = f.sheet("Sheet1")
            s.freeze_header()
            assert s.ws.freeze_panes == "A2"

            s.freeze_header(rows=2)
            assert s.ws.freeze_panes == "A3"

    def test_sheet_raises_on_missing_sheet(self, tmp_path):
        """存在しないシート名は SheetNotFoundError になることを確認する。"""
        with (
            ExcelWriter.create(tmp_path / "e.xlsx") as f,
            pytest.raises(SheetNotFoundError),
        ):
            f.sheet("存在しないシート")


class TestSheetApiBoundary:
    @pytest.mark.parametrize("col", ["A", "AA", 27])
    def test_moved_cell_and_format_methods(self, tmp_path, col):
        with ExcelWriter.create(tmp_path / "format.xlsx") as writer:
            sheet = writer.sheet("Sheet1")
            sheet.write_cell(2, col, 1000)
            sheet.set_fill(2, col, "FFFF00")
            sheet.set_column_width(col, 20)
            sheet.set_number_format(2, col, "#,##0")
            sheet.set_bold(2, col)
            cell = sheet.ws.cell(row=2, column=27 if col in ("AA", 27) else 1)
            assert cell.value == 1000
            assert cell.number_format == "#,##0"
            assert cell.font.bold

    def test_writer_has_no_sheet_level_methods(self, tmp_path):
        names = (
            "write_cell",
            "set_fill",
            "set_column_width",
            "set_number_format",
            "set_bold",
            "transfer_by_key",
        )
        with ExcelWriter.create(tmp_path / "boundary.xlsx") as writer:
            assert not [name for name in names if hasattr(writer, name)]


class TestStructuredTable:
    """Sheet の構造化テーブル操作。"""

    def test_append_expands_table_and_matches_headers_after_save(self, tmp_path):
        path = tmp_path / "append_table.xlsx"
        with ExcelWriter.create(path) as writer:
            sheet = writer.sheet("Sheet1")
            sheet.write_rows(1, [["商品", "金額"], ["A", 100]])
            sheet.add_table("売上", "A1:B2")
            writer.save()

        with ExcelWriter(path) as writer:
            sheet = writer.sheet("Sheet1")
            sheet.append_to_table("売上", [{"金額": 200, "商品": "B"}])
            assert writer.written_ranges() == {"Sheet1": "A3:B3"}
            writer.save()

        workbook = load_workbook(path)
        worksheet = workbook["Sheet1"]
        assert worksheet.tables["売上"].ref == "A1:B3"
        assert worksheet["A3"].value == "B"
        assert worksheet["B3"].value == 200
        workbook.close()

    def test_clear_removes_only_data_and_shrinks_table_after_save(self, tmp_path):
        path = tmp_path / "clear_table.xlsx"
        with ExcelWriter.create(path) as writer:
            sheet = writer.sheet("Sheet1")
            sheet.write_rows(1, [["商品", "金額"], ["A", 100], ["B", 200]])
            sheet.add_table("売上", "A1:B3")
            sheet.clear_table("売上")
            assert sheet["A1"] == "商品"
            assert sheet["B1"] == "金額"
            assert sheet["A2"] is None
            assert writer.written_ranges() == {"Sheet1": "A1:B3"}
            writer.save()

        workbook = load_workbook(path)
        assert workbook["Sheet1"].tables["売上"].ref == "A1:B1"
        workbook.close()

    def test_replace_swaps_data_and_keeps_missing_header_blank(self, tmp_path):
        path = tmp_path / "replace_table.xlsx"
        with ExcelWriter.create(path) as writer:
            sheet = writer.sheet("Sheet1")
            sheet.write_rows(1, [["商品", "金額"], ["旧", 999], ["残ると困る", 888]])
            sheet.add_table("売上", "A1:B3")
            sheet.replace_table("売上", [{"商品": "新"}])
            assert sheet["A2"] == "新"
            assert sheet["B2"] == ""
            assert sheet["A3"] is None
            assert sheet.ws.tables["売上"].ref == "A1:B2"

    @pytest.mark.parametrize("name", ["売上 表", "1売上", "A1", "R1C1"])
    def test_invalid_name_raises_with_guidance(self, tmp_path, name):
        with (
            ExcelWriter.create(tmp_path / "invalid.xlsx") as writer,
            pytest.raises(InvalidTableNameError, match="空白を含めず"),
        ):
            writer.sheet("Sheet1").add_table(name, "A1:B2")

    def test_duplicate_and_missing_errors_are_specific(self, tmp_path):
        with ExcelWriter.create(tmp_path / "errors.xlsx") as writer:
            sheet = writer.sheet("Sheet1")
            sheet.write_rows(1, [["A", "B"], [1, 2]])
            sheet.add_table("既存", "A1:B2")
            with pytest.raises(TableAlreadyExistsError):
                sheet.add_table("既存", "A1:B2")
            with pytest.raises(TableNotFoundError, match="既存"):
                sheet.append_to_table("不在", [{"A": 3}])

    def test_unknown_key_raises_with_guidance(self, tmp_path):
        with ExcelWriter.create(tmp_path / "unknown_key.xlsx") as writer:
            sheet = writer.sheet("Sheet1")
            sheet.write_rows(1, [["商品", "金額"], ["A", 100]])
            sheet.add_table("売上", "A1:B2")
            with pytest.raises(ValueError, match="キー名を見出しに合わせて"):
                sheet.append_to_table("売上", [{"商品": "B", "数量": 2}])

    def test_replace_validates_before_clearing_existing_data(self, tmp_path):
        with ExcelWriter.create(tmp_path / "invalid_replace.xlsx") as writer:
            sheet = writer.sheet("Sheet1")
            sheet.write_rows(1, [["商品", "金額"], ["A", 100]])
            sheet.add_table("売上", "A1:B2")
            with pytest.raises(ValueError):
                sheet.replace_table("売上", [{"商品": "B", "数量": 2}])
            assert sheet["A2"] == "A"
            assert sheet["B2"] == 100

    def test_removed_table_methods_do_not_exist(self, tmp_path):
        with ExcelWriter.create(tmp_path / "removed.xlsx") as writer:
            sheet = writer.sheet("Sheet1")
            for name in ("table_names", "rename_table", "resize_table", "delete_table"):
                assert not hasattr(sheet, name)


class TestReadComputedRows:
    """read_computed_rows() のフォールバック判定を確認する。"""

    def test_formula_without_cached_value_uses_com(self, tmp_path):
        """キャッシュ値がない数式があれば COM で再計算する。"""
        path = tmp_path / "formula.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        ws.append(["値", "計算結果"])
        ws.append([10, "=A2*2"])
        wb.save(path)
        com = MagicMock()
        com.__enter__.return_value.read_rows.return_value = [(10, 20)]

        with (
            patch("comken.windows.handler.ExcelComHandler", return_value=com) as handler,
            ExcelReader(path) as reader,
        ):
            rows = reader.read_computed_rows("Sheet1")

        assert rows == [(10, 20)]
        handler.assert_called_once_with(path)
        com.__enter__.return_value.read_rows.assert_called_once_with("Sheet1", 2)

    def test_workbook_without_formula_does_not_use_com(self, excel_with_header):
        """数式がなければ openpyxl の結果を返し、COM を起動しない。"""
        with (
            patch("comken.windows.handler.ExcelComHandler") as handler,
            ExcelReader(excel_with_header) as reader,
        ):
            rows = reader.read_computed_rows("Sheet1")

        assert rows == [("A001", 1000, "山田"), ("A002", 2000, "佐藤")]
        handler.assert_not_called()


class TestColToNum:
    """内部の列記号変換の振る舞いを確認する。"""

    @pytest.mark.parametrize(
        ("letter", "expected"),
        [("A", 1), ("B", 2), ("Q", 17), ("Z", 26), ("AA", 27), ("AZ", 52)],
    )
    def test_converts_letter_to_number(self, letter, expected):
        assert col_to_num(letter) == expected

    def test_lowercase_is_allowed(self):
        assert col_to_num("q") == 17

    @pytest.mark.parametrize("letter", ["", "1", "A1", "あ"])
    def test_rejects_invalid_letter(self, letter):
        with pytest.raises(OriginalLibsError, match="列番号（1始まり）または列記号"):
            col_to_num(letter)


class TestExcelApiBoundaries:
    """Reader と Writer の公開 API 境界を確認する。"""

    def test_col_to_num_is_not_public(self):
        assert "col_to_num" not in comken.excel.__all__
        assert not hasattr(comken.excel, "col_to_num")

    def test_writer_rejects_read_only_argument(self, excel_with_header):
        """ExcelWriter は read_only 引数を公開しない。"""
        with pytest.raises(TypeError, match="read_only"):
            ExcelWriter(excel_with_header, read_only=True)

    def test_reader_has_no_sheet_method(self, excel_with_header):
        """ExcelReader は書き込み可能な Sheet を公開しない。"""
        with ExcelReader(excel_with_header) as reader:
            assert not hasattr(reader, "sheet")


class TestExcelWriterTransactionalSave:
    """ExcelWriter.save() の既存ファイル保護を確認する。"""

    def test_save_failure_preserves_existing_file(self, excel_with_header):
        """一時ファイルへの保存失敗時に既存ファイルを変更しない。"""
        original_bytes = excel_with_header.read_bytes()

        with ExcelWriter(excel_with_header) as writer:
            writer.sheet("Sheet1").write_cell(row=2, col=2, value=9999)
            with (
                patch.object(writer._wb, "save", side_effect=OSError("save failed")),
                pytest.raises(OSError, match="save failed"),
            ):
                writer.save()

        assert excel_with_header.read_bytes() == original_bytes
        assert list(excel_with_header.parent.glob(f".{excel_with_header.name}.*.tmp")) == []
