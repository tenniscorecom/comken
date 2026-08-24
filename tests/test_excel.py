"""現行のExcel API（Excel / Sheet / ExcelTable）の契約テスト。"""

import pytest

from comken.core.table import Table
from comken.exceptions import (
    DataSheetAccessError,
    ExcelFileNotFoundError,
    InvalidTableOperationError,
    SheetAlreadyExistsError,
    SheetNameError,
    UnsupportedFileSuffixError,
)
from comken.toolbox.excel import Excel


def test_excel_creates_and_reads_python_table(tmp_path) -> None:
    path = tmp_path / "book.xlsx"
    with Excel(path) as excel:
        sheet = excel.create_data_sheet("顧客")
        sheet.create_table("顧客", Table(["ID", "名前"], [{"ID": "001", "名前": "山田"}]))
    with Excel(path, read_only=True) as excel:
        assert excel.data_sheet("顧客").table().read().read() == [{"ID": "001", "名前": "山田"}]


def test_excel_replaces_table_without_saving_until_context_exit(tmp_path) -> None:
    path = tmp_path / "book.xlsx"
    with Excel(path) as excel:
        excel.create_data_sheet("顧客").create_table("顧客", Table(["ID"], [{"ID": "001"}]))
    with Excel(path) as excel:
        table = excel.data_sheet("顧客").table()
        table.replace([{"ID": "002"}])
        assert table.read().read() == [{"ID": "002"}]
    with Excel(path, read_only=True) as excel:
        assert excel.data_sheet("顧客").table().read().read() == [{"ID": "002"}]


def test_excel_rejects_ambiguous_table_name(tmp_path) -> None:
    path = tmp_path / "book.xlsx"
    with Excel(path) as excel:
        sheet = excel.create_data_sheet("顧客")
        sheet.create_table("基本", Table(["ID"], [{"ID": "001"}]), "A1")
        sheet.create_table("連絡", Table(["電話"], [{"電話": "000"}]), "D1")
        with pytest.raises(InvalidTableOperationError):
            sheet.table().read()


def test_excel_rejects_duplicate_data_sheet(tmp_path) -> None:
    with Excel(tmp_path / "book.xlsx") as excel:
        excel.create_data_sheet("顧客")
        with pytest.raises(SheetAlreadyExistsError):
            excel.create_data_sheet("顧客")


def test_excel_table_append_accepts_row_list_and_table(tmp_path) -> None:
    path = tmp_path / "book.xlsx"
    with Excel(path) as excel:
        table = excel.create_data_sheet("顧客").create_table("顧客", Table(["ID"], [{"ID": "001"}]))
        table.append({"ID": "002"})
        table.append([{"ID": "003"}])
        table.append(Table(["ID"], [{"ID": "004"}]))
    with Excel(path, read_only=True) as excel:
        assert excel.data_sheet("顧客").table().read().column("ID") == [
            "001",
            "002",
            "003",
            "004",
        ]


def test_excel_rejects_missing_read_only_file_and_non_excel_suffix(tmp_path) -> None:
    with pytest.raises(ExcelFileNotFoundError):
        Excel(tmp_path / "missing.xlsx", read_only=True)
    with pytest.raises(UnsupportedFileSuffixError):
        Excel(tmp_path / "book.csv")


def test_create_sheet_uses_name_as_is_and_supports_layout_api(tmp_path) -> None:
    path = tmp_path / "book.xlsx"
    with Excel(path) as excel:
        sheet = excel.create_sheet("集計")
        assert sheet.is_data_sheet is False
        sheet.set_column_width("A", 12)
        sheet.freeze_panes("B2")
        sheet.write_value("A1", "見出し")
        sheet.format("A1", bold=True)
    with Excel(path, read_only=True) as excel:
        restored = excel.sheet("集計")
        assert restored.read_value("A1") == "見出し"
        assert restored.read_value("A1") == "見出し"


def test_create_sheet_does_not_appear_in_list_data_sheets(tmp_path) -> None:
    path = tmp_path / "book.xlsx"
    with Excel(path) as excel:
        excel.create_data_sheet("顧客").create_table("顧客", Table(["ID"], [{"ID": "001"}]))
        excel.create_sheet("集計")
        assert excel.list_data_sheets() == ["PY_顧客"]


def test_create_sheet_allows_multiple_display_sheets(tmp_path) -> None:
    path = tmp_path / "book.xlsx"
    with Excel(path) as excel:
        excel.create_sheet("集計")
        excel.create_sheet("月次")
        display_names = [name for name in excel._workbook.sheetnames if not name.startswith("PY_")]
        assert "集計" in display_names
        assert "月次" in display_names


def test_create_sheet_rejects_duplicate_name(tmp_path) -> None:
    with Excel(tmp_path / "book.xlsx") as excel:
        excel.create_sheet("集計")
        with pytest.raises(SheetAlreadyExistsError):
            excel.create_sheet("集計")


def test_create_sheet_rejects_python_prefixed_name(tmp_path) -> None:
    with Excel(tmp_path / "book.xlsx") as excel, pytest.raises(SheetNameError):
        excel.create_sheet("PY_顧客")


def test_create_sheet_rejects_read_only_workbook(tmp_path) -> None:
    path = tmp_path / "book.xlsx"
    with Excel(path) as excel:
        excel.create_sheet("集計")
    with Excel(path, read_only=True) as excel, pytest.raises(RuntimeError):
        excel.create_sheet("別のシート")


def test_create_sheet_returns_sheet_that_supports_layout_api(tmp_path) -> None:
    path = tmp_path / "book.xlsx"
    with Excel(path) as excel:
        sheet = excel.create_sheet("集計")
        # 表示用シートでは table() は DataSheetAccessError
        with pytest.raises(DataSheetAccessError):
            sheet.table()
