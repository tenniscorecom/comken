"""CSV / Excel のデータ領域 API のテスト。"""

from datetime import UTC, datetime

import pytest

from comken.exceptions import DataSheetAccessError
from comken.toolbox.csv import CSV
from comken.toolbox.excel import Excel


class TestCSV:
    def test_read_replace_count_and_types(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        rows = [
            {
                "id": 1,
                "rate": 1.5,
                "enabled": True,
                "updated_at": datetime(2026, 8, 21, 10, 30, tzinfo=UTC),
                "note": "",
            }
        ]

        with CSV(path) as table:
            table.replace(rows)
            assert table.count() == 1
            assert table.read() == rows

    def test_replace_empty_makes_empty_table(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        CSV(path).replace([{"id": 1}])

        CSV(path).replace([])

        assert CSV(path).read() == []


class TestExcelTable:
    def test_read_replace_count_and_blank(self, tmp_path) -> None:
        path = tmp_path / "data.xlsx"
        rows = [{"id": 1, "name": "", "enabled": True}]

        with Excel(path) as excel:
            table = excel.sheet("data_Users").table()
            table.replace(rows)
            assert table.count() == 1
            assert table.read() == rows

        with Excel(path) as excel:
            assert excel.list_data_sheets() == ["data_Users"]
            assert excel.sheet("data_Users").table().read() == rows

    def test_data_sheet_rejects_cell_access(self, tmp_path) -> None:
        with Excel(tmp_path / "data.xlsx") as excel:
            sheet = excel.sheet("data_Users")

            with pytest.raises(DataSheetAccessError):
                sheet.write_value("A1", "禁止")

    def test_display_sheet_rejects_table_access(self, tmp_path) -> None:
        with Excel(tmp_path / "dashboard.xlsx") as excel:
            sheet = excel.sheet("Dashboard")

            with pytest.raises(DataSheetAccessError):
                sheet.table()

    def test_display_sheet_cell_range_and_format(self, tmp_path) -> None:
        path = tmp_path / "dashboard.xlsx"
        with Excel(path) as excel:
            sheet = excel.sheet("Dashboard")
            sheet.write_range("A1:B2", [["name", "value"], ["sales", 10]])
            sheet.format("A1", bold=True)
            sheet.set_background("A1", "FFFF00")
            sheet.freeze_panes("A2")
            assert sheet.read_range("A1:B2") == [{"name": "sales", "value": 10}]
            assert sheet.get_used_range() == ("A1", "B2")
