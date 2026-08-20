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
from openpyxl.worksheet.table import Table, TableStyleInfo

import comken.toolbox.excel
from comken import dry_run
from comken.core.config import Config
from comken.core.data import col_to_num
from comken.exceptions import (
    ComkenError,
    EmptyHeaderCellError,
    ExcelApplicationNotAvailableError,
    ExcelError,
    FileFormatMismatchError,
    InvalidTableNameError,
    LastSheetDeletionError,
    SheetAlreadyExistsError,
    SheetNotFoundError,
    TableAlreadyExistsError,
    TableNotAvailableInReadOnlyError,
    TableNotFoundError,
    TransferDestinationColumnNotFoundError,
    TransferKeyColumnNotFoundError,
    TransferSourceColumnNotFoundError,
    UnsupportedFileSuffixError,
)
from comken.toolbox.excel import ExcelReader, ExcelWriter
from comken.toolbox.excel.sheet import DEFAULT_TABLE_STYLE
from comken.toolbox.windows.handler import ExcelComHandler


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
            pytest.raises(ComkenError, match="例: 1"),
        ):
            writer.sheet("Sheet1").write_cell(row=2, col=col, value="値")


class TestExcelComHandlerColumn:
    def test_quits_excel_when_application_setup_fails(self, tmp_path):
        """Excel 起動後のプロパティ設定に失敗してもプロセスを終了する。"""

        class FailingExcel:
            def __init__(self) -> None:
                self.is_quit = False

            @property
            def Visible(self) -> bool:
                return False

            @Visible.setter
            def Visible(self, value: object) -> None:
                raise RuntimeError("setup failed")

            def Quit(self) -> None:
                self.is_quit = True

        path = tmp_path / "book.xlsx"
        path.touch()
        excel = FailingExcel()

        with (
            patch("comken.toolbox.windows.handler.win32com.client.DispatchEx", return_value=excel),
            pytest.raises(RuntimeError, match="setup failed"),
        ):
            ExcelComHandler(path)

        assert excel.is_quit is True

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
        handler.last_row = MagicMock(return_value=5)

        matched = handler.transfer_by_letter(
            "Sheet1",
            key_col="A",
            lookup={
                "1001": {"顧客名": "株式会社A", "金額": 1000},
                "1002": {"顧客名": "株式会社C", "金額": 1500},
                "A002": {"顧客名": "株式会社B", "金額": 2000},
            },
            mapping={"顧客名": "B", "金額": "C"},
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
        handler.last_row = MagicMock(return_value=3)

        with pytest.raises(ExcelError, match="3行目"):
            handler.transfer_by_letter(
                "Sheet1",
                key_col="A",
                lookup={"1001": {"値": "A"}, "1002": {"値": "B"}},
                mapping={"値": "B"},
            )


class TestExcelComHandlerBulkRead:
    """COM 読み取りが範囲一括で行われることのテスト。"""

    @staticmethod
    def _sheet_with(block: tuple[tuple, ...], rows: int, cols: int):
        """指定の値を Range でまとめて返す偽シートと、Range の呼び出し記録を返す。"""
        calls: list[tuple] = []

        class FakeRange:
            def __init__(self, start, end) -> None:
                calls.append((start, end))
                self._first_row = start[0]
                self._last_row = end[0]

            @property
            def Value(self):
                return tuple(block[self._first_row - 1 : self._last_row])

        sheet = MagicMock()
        sheet.Cells.side_effect = lambda row, col: (row, col)
        sheet.Range.side_effect = FakeRange
        sheet.UsedRange = SimpleNamespace(
            Row=1,
            Column=1,
            Rows=SimpleNamespace(Count=rows),
            Columns=SimpleNamespace(Count=cols),
        )
        return sheet, calls

    def _handler(self, sheet, last_row: int, headers=None):
        handler = ExcelComHandler.__new__(ExcelComHandler)
        handler._sheet = MagicMock(return_value=sheet)
        handler.last_row = MagicMock(return_value=last_row)
        handler._headers = headers
        return handler

    def test_read_rows_uses_one_range_call(self):
        """行数×列数ぶん COM を往復せず、1回の Range で読むことを確認する。"""
        block = (("見出A", "見出B"), ("a1", "b1"), ("a2", "b2"))
        sheet, calls = self._sheet_with(block, rows=3, cols=2)
        handler = self._handler(sheet, last_row=3)

        assert handler.read_rows("Sheet1") == [("a1", "b1"), ("a2", "b2")]
        assert len(calls) == 1  # セル単位の走査に戻したらここが増える

    def test_read_rows_as_dicts_reads_header_and_body_in_two_calls(self):
        """見出しと本体をそれぞれ1回ずつの Range で読むことを確認する。"""
        block = (("注文番号", "金額"), ("A001", 1000), ("A002", 2000))
        sheet, calls = self._sheet_with(block, rows=3, cols=2)
        handler = self._handler(sheet, last_row=3)

        assert handler.read_rows_as_dicts("Sheet1") == [
            {"注文番号": "A001", "金額": 1000},
            {"注文番号": "A002", "金額": 2000},
        ]
        assert len(calls) == 2

    def test_single_cell_range_is_normalised(self):
        """1セルだけの範囲でも行のタプルとして返ることを確認する。"""
        # Range.Value は1セルのときスカラーを返すため、そろえないと呼び出し側が壊れる。
        sheet, _ = self._sheet_with((("値",),), rows=1, cols=1)
        sheet.Range.side_effect = lambda start, end: SimpleNamespace(Value="値")
        handler = self._handler(sheet, last_row=1)

        assert handler.read_rows("Sheet1", min_row=1) == [("値",)]

    def test_empty_range_returns_no_rows(self):
        """データ行が無ければ Range を呼ばずに空を返すことを確認する。"""
        sheet, calls = self._sheet_with((("見出",),), rows=1, cols=1)
        handler = self._handler(sheet, last_row=1)

        assert handler.read_rows("Sheet1", min_row=2) == []
        assert calls == []


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
    """Sheet.transfer_by_letter（openpyxl 版のキー突合転記）のテスト。"""

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
            matched = f.sheet("T_data").transfer_by_letter(
                key_col="A", lookup=lookup, mapping={"顧客名": "B", "金額": "C"}
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
            matched = f.sheet("T_data").transfer_by_letter(
                key_col="A", lookup=lookup, mapping={"顧客名": "B"}
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
            matched = f.sheet("T_data").transfer_by_letter(
                key_col="A", lookup=lookup, mapping={"顧客名": "B"}
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
            matched = f.sheet("T_data").transfer_by_letter(
                key_col=1, lookup=lookup, mapping={"顧客名": "B"}
            )

        assert matched == 1

    def test_raises_on_missing_sheet(self, transfer_excel):
        """存在しないシートを指定すると SheetNotFoundError になることを確認する。"""
        with ExcelWriter(transfer_excel) as f, pytest.raises(SheetNotFoundError):
            f.sheet("存在しない").transfer_by_letter(key_col="A", lookup={}, mapping={})


class TestTransferByMapping:
    """Sheet.transfer_by_mapping（列名で指定するキー突合転記）のテスト。"""

    @pytest.fixture
    def transfer_excel(self, tmp_path):
        wb = Workbook()
        ws = wb.active
        ws.title = "T_data"
        ws.append(["受注番号", "顧客名", "請求額"])
        ws.append(["A001", None, None])
        ws.append(["A002", None, None])
        ws.append(["Z999", None, None])
        path = tmp_path / "transfer_by_mapping.xlsx"
        wb.save(path)
        return path

    def test_transfers_config_mapping_in_source_to_destination_direction(
        self, transfer_excel, tmp_path
    ):
        lookup = {
            "A001": {"取引先": "株式会社A", "金額": 1000},
            "A002": {"取引先": "株式会社B", "金額": 2000},
        }
        ini = tmp_path / "config.ini"
        ini.write_text("[受注_MAPPING]\n取引先 = 顧客名\n金額 = 請求額\n", encoding="utf-8")
        config_mapping = Config(ini).受注_MAPPING

        with ExcelWriter(transfer_excel) as f:
            matched = f.sheet("T_data").transfer_by_mapping(
                key_col="受注番号", lookup=lookup, mapping=config_mapping
            )
            f.save()

        assert matched == 2
        wb = load_workbook(transfer_excel)
        ws = wb["T_data"]
        assert ws["B2"].value == "株式会社A"
        assert ws["C3"].value == 2000
        assert ws["B4"].value is None
        wb.close()

    def test_missing_destination_raises_before_any_cell_or_file_is_changed(self, transfer_excel):
        lookup = {"A001": {"取引先": "株式会社A", "金額": 1000}}

        with ExcelWriter(transfer_excel) as f:
            sheet = f.sheet("T_data")
            with pytest.raises(TransferDestinationColumnNotFoundError) as error:
                sheet.transfer_by_mapping(
                    key_col="受注番号",
                    lookup=lookup,
                    mapping={"取引先": "顧客名", "金額": "存在しない列"},
                )
            assert sheet.ws["B2"].value is None

        wb = load_workbook(transfer_excel)
        assert wb["T_data"]["B2"].value is None
        wb.close()
        assert str(error.value) == (
            "転記先の列がExcelに見つかりません: 存在しない列\n"
            "転記先に存在する列: 受注番号, 顧客名, 請求額\n"
            "Excelのヘッダー行と config.ini のマッピング右側を確認してください。"
        )

    def test_missing_source_raises_before_transfer(self, transfer_excel):
        lookup = {"A001": {"取引先": "株式会社A"}}

        with ExcelWriter(transfer_excel) as f, pytest.raises(TransferSourceColumnNotFoundError):
            f.sheet("T_data").transfer_by_mapping(
                key_col="受注番号",
                lookup=lookup,
                mapping={"取引先": "顧客名", "金額": "請求額"},
            )

    def test_missing_key_column_raises(self, transfer_excel):
        with ExcelWriter(transfer_excel) as f, pytest.raises(TransferKeyColumnNotFoundError):
            f.sheet("T_data").transfer_by_mapping(
                key_col="存在しないキー",
                lookup={"A001": {"取引先": "株式会社A"}},
                mapping={"取引先": "顧客名"},
            )

    def test_uses_header_row_other_than_first(self, tmp_path):
        wb = Workbook()
        ws = wb.active
        ws.title = "T_data"
        ws.append(["帳票タイトル"])
        ws.append(["受注番号", "顧客名"])
        ws.append(["A001", None])
        path = tmp_path / "header_row_2.xlsx"
        wb.save(path)

        with ExcelWriter(path) as f:
            matched = f.sheet("T_data").transfer_by_mapping(
                key_col="受注番号",
                lookup={"A001": {"取引先": "株式会社A"}},
                mapping={"取引先": "顧客名"},
                header_row=2,
            )
            f.save()

        assert matched == 1
        wb = load_workbook(path)
        assert wb["T_data"]["B3"].value == "株式会社A"
        wb.close()


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
    def test_formula_validation_apis_are_not_exposed(self, tmp_path):
        with ExcelWriter.create(tmp_path / "boundary.xlsx") as writer:
            assert not hasattr(writer, "written_ranges")
        assert not hasattr(ExcelComHandler, "recalculate")

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
            "transfer_by_letter",
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


class TestReadTable:
    """ExcelBase.read_table() の挙動確認。"""

    def test_reads_table_with_headers(self, tmp_path):
        """ヘッダー付きの構造化テーブルを読み、キーと値が一致する。"""
        path = tmp_path / "table_basic.xlsx"
        with ExcelWriter.create(path) as writer:
            sheet = writer.sheet("Sheet1")
            sheet.write_rows(1, [["品目", "数量"], ["A", 100], ["B", 200]])
            sheet.add_table("売上", "A1:B3")
            writer.save()

        with ExcelReader(path, tables=True) as reader:
            rows = reader.read_table("Sheet1", "売上")

        assert rows == [{"品目": "A", "数量": 100}, {"品目": "B", "数量": 200}]

    def test_reads_table_when_not_at_top_of_sheet(self, tmp_path):
        """シートの途中にあるテーブルも、セル範囲を意識せず読み取れる。"""
        path = tmp_path / "table_middle.xlsx"
        with ExcelWriter.create(path) as writer:
            sheet = writer.sheet("Sheet1")
            sheet.write_rows(1, [["タイトル"], ["", "", ""], ["", "", ""], ["", "", ""]])
            sheet.write_rows(5, [["品目", "数量"], ["A", 100], ["B", 200], ["C", 300]])
            sheet.add_table("売上", "A5:B8")
            writer.save()

        with ExcelReader(path, tables=True) as reader:
            rows = reader.read_table("Sheet1", "売上")

        assert rows == [
            {"品目": "A", "数量": 100},
            {"品目": "B", "数量": 200},
            {"品目": "C", "数量": 300},
        ]

    def test_reads_appended_rows_after_save(self, tmp_path):
        """append_to_table() で行を追加した後も、追加した行まで読める。"""
        path = tmp_path / "table_appended.xlsx"
        with ExcelWriter.create(path) as writer:
            sheet = writer.sheet("Sheet1")
            sheet.write_rows(1, [["品目", "数量"], ["A", 100]])
            sheet.add_table("売上", "A1:B2")
            writer.save()

        with ExcelWriter(path) as writer:
            sheet = writer.sheet("Sheet1")
            sheet.append_to_table("売上", [{"品目": "B", "数量": 200}, {"品目": "C", "数量": 300}])
            writer.save()

        with ExcelReader(path, tables=True) as reader:
            rows = reader.read_table("Sheet1", "売上")

        assert rows == [
            {"品目": "A", "数量": 100},
            {"品目": "B", "数量": 200},
            {"品目": "C", "数量": 300},
        ]

    def test_missing_table_raises_with_list(self, tmp_path):
        """テーブル名を間違えると、既存テーブル名一覧つきの TableNotFoundError。"""
        path = tmp_path / "table_missing.xlsx"
        with ExcelWriter.create(path) as writer:
            sheet = writer.sheet("Sheet1")
            sheet.write_rows(1, [["品目", "数量"], ["A", 100]])
            sheet.add_table("売上", "A1:B2")
            writer.save()

        with (
            ExcelReader(path, tables=True) as reader,
            pytest.raises(TableNotFoundError, match="売上"),
        ):
            reader.read_table("Sheet1", "存在しない")

    def test_read_only_reader_rejects_read_table(self, excel_with_header):
        """read_only で開いた ExcelReader では TableNotAvailableInReadOnlyError。"""
        with (
            ExcelReader(excel_with_header) as reader,
            pytest.raises(TableNotAvailableInReadOnlyError, match="tables=True"),
        ):
            reader.read_table("Sheet1", "なんでも")

    def test_writer_can_read_table(self, tmp_path):
        """ExcelWriter で開いた場合も read_table() を使える。"""
        path = tmp_path / "table_writer.xlsx"
        with ExcelWriter.create(path) as writer:
            sheet = writer.sheet("Sheet1")
            sheet.write_rows(1, [["品目", "数量"], ["A", 100]])
            sheet.add_table("売上", "A1:B2")
            writer.save()

        with ExcelWriter(path) as writer:
            rows = writer.read_table("Sheet1", "売上")

        assert rows == [{"品目": "A", "数量": 100}]

    def test_excludes_totals_row(self, tmp_path):
        """集計行（totalsRow）を持つテーブルで、集計行がデータに含まれない。"""
        path = tmp_path / "table_totals.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        ws["A1"] = "品目"
        ws["B1"] = "数量"
        ws["A2"] = "A"
        ws["B2"] = 100
        ws["A3"] = "B"
        ws["B3"] = 200
        ws["A4"] = "合計"
        ws["B4"] = "=SUM(B2:B3)"
        table = Table(displayName="売上", ref="A1:B4", totalsRowCount=1)
        table.tableStyleInfo = TableStyleInfo(
            name=DEFAULT_TABLE_STYLE,
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )
        ws.add_table(table)
        wb.save(path)

        with ExcelReader(path, tables=True) as reader:
            rows = reader.read_table("Sheet1", "売上")

        assert rows == [{"品目": "A", "数量": 100}, {"品目": "B", "数量": 200}]

    def test_partially_empty_header_raises(self, tmp_path):
        """見出しの一部だけが空なら止める。

        黙って読むと、その列だけキーが None の辞書が静かに流れていく。
        read_rows_as_dicts() と同じ扱いにそろえる。
        """
        path = tmp_path / "table_broken_header.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        ws["A1"] = "品目"
        ws["C1"] = "担当"  # B1 を空のままにする
        ws["A2"] = "A"
        ws["B2"] = 100
        ws["C2"] = "田中"
        ws.add_table(Table(displayName="欠け", ref="A1:C2"))
        wb.save(path)

        with ExcelReader(path, tables=True) as reader, pytest.raises(EmptyHeaderCellError):
            reader.read_table("Sheet1", "欠け")

    def test_partially_empty_header_reports_actual_column(self, tmp_path):
        """空欄の列番号は、テーブルが途中から始まっても実際の列で報告する。"""
        path = tmp_path / "table_broken_header_offset.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        ws["C1"] = "品目"
        ws["E1"] = "担当"  # D1 を空のままにする
        ws["C2"] = "A"
        ws["D2"] = 100
        ws["E2"] = "田中"
        ws.add_table(Table(displayName="ずれ", ref="C1:E2"))
        wb.save(path)

        with ExcelReader(path, tables=True) as reader, pytest.raises(EmptyHeaderCellError) as e:
            reader.read_table("Sheet1", "ずれ")

        assert "[4]" in str(e.value)  # D 列＝4列目


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
            patch("comken.toolbox.windows.handler.ExcelComHandler", return_value=com) as handler,
            ExcelReader(path) as reader,
        ):
            rows = reader.read_computed_rows("Sheet1")

        assert rows == [(10, 20)]
        handler.assert_called_once_with(path)
        com.__enter__.return_value.read_rows.assert_called_once_with("Sheet1", 2)

    def test_workbook_without_formula_does_not_use_com(self, excel_with_header):
        """数式がなければ openpyxl の結果を返し、COM を起動しない。"""
        with (
            patch("comken.toolbox.windows.handler.ExcelComHandler") as handler,
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
        with pytest.raises(ComkenError, match="列番号（1始まり）または列記号"):
            col_to_num(letter)


class TestExcelApiBoundaries:
    """Reader と Writer の公開 API 境界を確認する。"""

    def test_col_to_num_is_not_public(self):
        assert "col_to_num" not in comken.toolbox.excel.__all__
        assert not hasattr(comken.toolbox.excel, "col_to_num")

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


class TestExcelComHandlerLocalCopy:
    """ExcelComHandler のローカルコピー挙動。

    COM を起動しない境界で、閾値・保存先・close での一時ファイル削除を確認する。
    ``__init__`` 全体をモック化せず ``__new__`` でフィールドだけ埋めて検証する。
    """

    def test_save_uses_save_when_working_path_matches_original(self, tmp_path):
        """ローカルコピーせず開いたときは ``wb.Save()`` で保存する。"""
        original = tmp_path / "data.xlsx"
        original.touch()
        wb = MagicMock()
        wb.FileFormat = 51  # xlOpenXMLWorkbook

        handler = ExcelComHandler.__new__(ExcelComHandler)
        handler._wb = wb
        handler._original_path = original
        handler._working_path = original
        handler._tmp = None

        handler.save()

        wb.Save.assert_called_once_with()
        wb.SaveAs.assert_not_called()

    def test_save_uses_save_as_to_original_when_local_copy_was_used(self, tmp_path):
        """ローカルコピーで開いたときは元の場所へ ``SaveAs`` する（最重要）。"""
        original = tmp_path / "data.xlsx"
        original.touch()
        local = tmp_path / "tmp.xlsx"
        local.touch()
        wb = MagicMock()
        wb.FileFormat = 51

        handler = ExcelComHandler.__new__(ExcelComHandler)
        handler._wb = wb
        handler._original_path = original
        handler._working_path = local
        handler._tmp = local

        handler.save()

        wb.Save.assert_not_called()
        wb.SaveAs.assert_called_once_with(str(original), FileFormat=51)

        handler.save()

        wb.Save.assert_called_once_with()
        wb.SaveAs.assert_called_once_with(str(original), FileFormat=51)

    def test_save_raises_on_format_mismatch_when_local_copy_used(self, tmp_path):
        """ローカルコピー経路で、保存先拡張子とワークブック形式が食い違うとエラー。"""
        original = tmp_path / "data.xlsm"
        original.touch()
        local = tmp_path / "tmp.xlsx"
        local.touch()
        wb = MagicMock()
        wb.FileFormat = 51  # xlsx 形式なのに保存先拡張子は .xlsm

        handler = ExcelComHandler.__new__(ExcelComHandler)
        handler._wb = wb
        handler._original_path = original
        handler._working_path = local
        handler._tmp = local

        with pytest.raises(FileFormatMismatchError, match="xlsm"):
            handler.save()

    @pytest.mark.parametrize(("suffix", "file_format"), [(".xltx", 53), (".xltm", 54)])
    def test_save_raises_on_template_format_mismatch(self, tmp_path, suffix, file_format):
        """テンプレート形式でも拡張子と FileFormat の不一致を見逃さない。"""
        original = tmp_path / f"data{suffix}"
        original.touch()
        handler = ExcelComHandler.__new__(ExcelComHandler)
        handler._wb = MagicMock(FileFormat=file_format)
        handler._original_path = original
        handler._working_path = tmp_path / f"tmp{suffix}"
        handler._tmp = handler._working_path

        with pytest.raises(FileFormatMismatchError, match=suffix.removeprefix(".")):
            handler.save()

    def test_save_dry_run_does_not_call_com(self, tmp_path):
        """dry-run ではローカルコピー経路でも COM の保存処理を呼ばない。"""
        original = tmp_path / "data.xlsx"
        handler = ExcelComHandler.__new__(ExcelComHandler)
        handler._wb = MagicMock(FileFormat=51)
        handler._original_path = original
        handler._working_path = tmp_path / "tmp.xlsx"
        handler._tmp = handler._working_path

        with dry_run():
            handler.save()

        handler._wb.Save.assert_not_called()
        handler._wb.SaveAs.assert_not_called()

    def test_save_as_dry_run_does_not_call_com(self, tmp_path):
        """save_as も dry-run では SaveAs を呼ばない（save() と同じ扱い）。"""
        handler = ExcelComHandler.__new__(ExcelComHandler)
        handler._wb = MagicMock(FileFormat=51)
        handler._original_path = tmp_path / "data.xlsx"

        with dry_run():
            handler.save_as(tmp_path / "out.xlsx")

        handler._wb.SaveAs.assert_not_called()

    def test_save_as_dry_run_raises_on_format_mismatch(self, tmp_path):
        """dry-run でも拡張子と FileFormat の不一致はエラーにする。"""
        handler = ExcelComHandler.__new__(ExcelComHandler)
        handler._wb = MagicMock(FileFormat=51)  # xlsx 形式

        with dry_run(), pytest.raises(FileFormatMismatchError, match="xlsm"):
            handler.save_as(tmp_path / "out.xlsm")

        handler._wb.SaveAs.assert_not_called()

    def test_close_removes_local_copy(self, tmp_path):
        """``close()`` は Excel を閉じた後にローカルコピーを削除する。"""
        original = tmp_path / "data.xlsx"
        original.touch()
        local = tmp_path / "tmp.xlsx"
        local.write_text("data", encoding="utf-8")

        wb = MagicMock()
        excel = MagicMock()
        handler = ExcelComHandler.__new__(ExcelComHandler)
        handler._wb = wb
        handler._excel = excel
        handler._original_path = original
        handler._working_path = local
        handler._tmp = local

        handler.close()

        wb.Close.assert_called_once_with(SaveChanges=False)
        excel.Quit.assert_called_once_with()
        assert not local.exists()
        assert handler._tmp is None
        assert handler._excel is None
        assert handler._wb is None

    def test_close_is_idempotent_on_double_call(self, tmp_path):
        """``close()`` を2回呼んでも Excel.Quit が二重に走らない（一時ファイル削除も冪等）。"""
        original = tmp_path / "data.xlsx"
        original.touch()
        local = tmp_path / "tmp.xlsx"
        local.write_text("data", encoding="utf-8")

        wb = MagicMock()
        excel = MagicMock()
        handler = ExcelComHandler.__new__(ExcelComHandler)
        handler._wb = wb
        handler._excel = excel
        handler._original_path = original
        handler._working_path = local
        handler._tmp = local

        handler.close()
        handler.close()

        excel.Quit.assert_called_once_with()
        assert not local.exists()

    def test_close_removes_local_copy_when_quit_fails(self, tmp_path):
        """Quit が失敗してもローカルコピーは残さない。"""
        local = tmp_path / "tmp.xlsx"
        local.write_text("data", encoding="utf-8")
        handler = ExcelComHandler.__new__(ExcelComHandler)
        handler._wb = MagicMock()
        handler._excel = MagicMock()
        handler._excel.Quit.side_effect = OSError("quit failed")
        handler._tmp = local

        with pytest.raises(OSError, match="quit failed"):
            handler.close()

        assert not local.exists()

    def test_close_retries_local_copy_cleanup(self, tmp_path):
        """一時ファイル削除に一度失敗しても次の close で再試行する。"""
        local = tmp_path / "tmp.xlsx"
        local.touch()
        handler = ExcelComHandler.__new__(ExcelComHandler)
        handler._wb = None
        handler._excel = None
        handler._tmp = local

        with patch.object(Path, "unlink", side_effect=[OSError("locked"), None]) as unlink:
            handler.close()
            assert handler._tmp == local
            handler.close()

        assert unlink.call_count == 2
        assert handler._tmp is None

    def test_init_removes_local_copy_when_excel_is_unavailable(self, tmp_path):
        """DispatchEx 失敗時は Open 前でもローカルコピーを残さない。"""
        original = tmp_path / "data.xlsx"
        original.touch()
        local = tmp_path / "tmp.xlsx"
        local.touch()

        with (
            patch(
                "comken.toolbox.windows.handler.copy_to_local_if_large",
                return_value=(local, local),
            ),
            patch(
                "comken.toolbox.windows.handler.win32com.client.DispatchEx",
                side_effect=OSError("Excel unavailable"),
            ),
            pytest.raises(ExcelApplicationNotAvailableError, match="Excel"),
        ):
            ExcelComHandler(original)

        assert not local.exists()


class TestExcelBaseLocalCopyCleanup:
    """openpyxl で開けなかった場合の一時コピー後始末。"""

    def test_init_removes_local_copy_when_load_fails(self, tmp_path):
        original = tmp_path / "data.xlsx"
        original.touch()
        local = tmp_path / "tmp.xlsx"
        local.touch()

        with (
            patch(
                "comken.toolbox.excel.base.copy_to_local_if_large",
                return_value=(local, local),
            ),
            patch("comken.toolbox.excel.base.load_workbook", side_effect=OSError("load failed")),
            pytest.raises(OSError, match="load failed"),
        ):
            ExcelReader(original)


class TestExcelWriterSavePassword:
    """ExcelWriter.save() のパスワード保存まわり。"""

    def test_save_without_password_does_not_use_com(
        self, tmp_path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """パスワードなしでは ExcelComHandler を起動しないこと。"""
        path = tmp_path / "book.xlsx"
        with ExcelWriter.create(path) as writer:
            writer.sheet("Sheet1").write_cell(row=1, col=1, value="値")
            with patch("comken.toolbox.windows.handler.ExcelComHandler") as com_cls:
                writer.save()
                com_cls.assert_not_called()
        assert path.exists()

    def test_save_with_password_calls_com_handler_with_passwords(self, tmp_path) -> None:
        """パスワードありでは ExcelComHandler.save_as() が read_pw / write_pw 付きで呼ばれる。"""
        path = tmp_path / "book.xlsx"
        with ExcelWriter.create(path) as writer:
            writer.sheet("Sheet1").write_cell(row=1, col=1, value="値")
            with patch("comken.toolbox.windows.handler.ExcelComHandler") as com_cls:
                com_instance = MagicMock()
                com_instance.save_as.side_effect = lambda *args, **kwargs: path.touch()
                com_cls.return_value.__enter__.return_value = com_instance
                writer.save(read_pw="r", write_pw="w")
                com_instance.save_as.assert_called_once()
                _, kwargs = com_instance.save_as.call_args
                assert kwargs["read_pw"] == "r"
                assert kwargs["write_pw"] == "w"
        assert path.exists()

    def test_password_save_uses_matching_suffix_in_tmp(self, tmp_path) -> None:
        """パスワード保存時の一時ファイルは save_path と同じ拡張子を持つこと。

        COM は拡張子で形式を判定するため、.xlsm を .tmp で保存すると
        FileFormatMismatchError で失敗する（実際に起きたバグ）。
        """
        path = tmp_path / "book.xlsm"
        with ExcelWriter.create(path) as writer:
            writer.sheet("Sheet1").write_cell(row=1, col=1, value="値")
            with patch("comken.toolbox.windows.handler.ExcelComHandler") as com_cls:
                com_instance = MagicMock()
                com_instance.save_as.side_effect = lambda *args, **kwargs: path.touch()
                com_cls.return_value.__enter__.return_value = com_instance
                writer.save(write_pw="w")
                tmp_path_arg = Path(com_cls.call_args.args[0])
                assert tmp_path_arg.suffix == ".xlsm"
        assert path.exists()

    def test_save_dry_run_creates_no_files_and_no_com(
        self, tmp_path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """dry-run では保存せず、COM も起動せず、パスワードはログに残らないこと。"""
        path = tmp_path / "book.xlsx"
        with (
            dry_run(),
            patch("comken.toolbox.windows.handler.ExcelComHandler") as com_cls,
            ExcelWriter.create(path) as writer,
        ):
            writer.sheet("Sheet1").write_cell(row=1, col=1, value="値")
            writer.save(read_pw="secret", write_pw="secret")
            com_cls.assert_not_called()
        assert not path.exists()
        # パスワードがログに出ていないこと（秘匿値の漏洩を防ぐ）
        for record in caplog.records:
            assert "secret" not in record.getMessage()

    def test_save_raises_when_file_missing(self, tmp_path, monkeypatch) -> None:
        """保存後にファイルが無いと ExcelSaveNotCompletedError を投げること。"""
        from comken.exceptions import ExcelSaveNotCompletedError

        path = tmp_path / "book.xlsx"
        with ExcelWriter.create(path) as writer:
            writer.sheet("Sheet1").write_cell(row=1, col=1, value="値")
            # save_path だけ False にして、保存後の exists() チェックを失敗させる。
            # ピンポイントで上書きしないと parent.exists() なども巻き込む
            # （openpyxl や tempfile が mkdir を試みると失敗するため）
            real_exists = Path.exists

            def fake_exists(self, *args, **kwargs):
                if str(self) == str(path):
                    return False
                return real_exists(self, *args, **kwargs)

            monkeypatch.setattr(Path, "exists", fake_exists)
            with pytest.raises(ExcelSaveNotCompletedError):
                writer.save()
