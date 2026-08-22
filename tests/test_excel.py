"""現行のExcel API（Excel / Sheet / ExcelTable）の契約テスト。"""

import pytest

from comken.core.table import Table
from comken.exceptions import (
    ExcelFileNotFoundError,
    InvalidTableOperationError,
    SheetAlreadyExistsError,
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
