"""CSV / Excel のデータ領域 API のテスト。"""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from comken import dry_run
from comken.core.table import Table
from comken.exceptions import DataSheetAccessError, TableColumnMismatchError
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
        with CSV(path) as csv_file:
            csv_file.replace([{"id": 1}])

        with CSV(path) as csv_file:
            csv_file.replace([])

        with CSV(path) as csv_file:
            assert csv_file.read() == []

    def test_empty_table_preserves_header_and_dry_run_does_not_save(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        with CSV(path) as csv_file:
            csv_file.replace(Table(["id", "name"], []))
        with CSV(path) as csv_file:
            assert csv_file.read().columns == ["id", "name"]

        with dry_run(), CSV(path) as csv_file:
            csv_file.replace(Table(["changed"], []))
        with CSV(path) as csv_file:
            assert csv_file.read().columns == ["id", "name"]


class TestExcelTable:
    def test_read_replace_count_and_blank(self, tmp_path) -> None:
        path = tmp_path / "data.xlsx"
        rows = [{"id": 1, "name": "", "enabled": True}]

        types = {"id": int, "enabled": lambda value: str(value).casefold() == "true"}
        with Excel(path, types=types) as excel:
            table = excel.create_data_sheet("Users").create_table(
                "Users", Table(["id", "name", "enabled"], rows)
            )
            assert table.count() == 1
            assert table.read() == rows

        with Excel(path, types=types) as excel:
            assert excel.list_data_sheets() == ["PY_Users"]
            assert excel.data_sheet("Users").table().read() == rows

    def test_data_sheet_rejects_cell_access(self, tmp_path) -> None:
        with Excel(tmp_path / "data.xlsx") as excel:
            sheet = excel.create_data_sheet("Users")

            with pytest.raises(DataSheetAccessError):
                sheet.write_value("A1", "禁止")

    def test_empty_replace_with_omitted_non_formula_column_raises(self, tmp_path) -> None:
        """``replace()`` で非数式列を省くと、データ欠落を防ぐため ``TableColumnMismatchError``。"""
        path = tmp_path / "data.xlsx"
        with Excel(path) as excel:
            table = excel.create_data_sheet("Users").create_table(
                "Users", Table(["id", "name"], [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}])
            )
            with pytest.raises(TableColumnMismatchError) as exc_info:
                table.replace(Table(["id"], []))
            # 省かれた非数式列「name」がエラーに含まれている
            assert "name" in str(exc_info.value)
            # 既存データはそのまま残っている（上書きされていない）
            assert table._worksheet["A2"].value == 1
            assert table._worksheet["B2"].value == "A"

    def test_table_read_ignores_formula_outside_actual_ref(self, tmp_path) -> None:
        path = tmp_path / "bounded.xlsx"
        with Excel(path) as excel:
            table = excel.create_data_sheet("Users").create_table(
                "Users", Table(["id"], [{"id": 1}])
            )
            table._worksheet["C2"] = "=1+1"
            with patch.object(excel, "_read_range_with_com") as read_with_com:
                result = table.read()

            assert result.read_rows() == [{"id": "1"}]
            read_with_com.assert_not_called()

    def test_cached_formula_stays_on_openpyxl(self, tmp_path) -> None:
        path = tmp_path / "cached.xlsx"
        with Excel(path) as excel:
            table = excel.create_data_sheet("Users").create_table(
                "Users", Table(["id", "total"], [{"id": 1, "total": 2}])
            )
        with Excel(path) as excel:
            table = excel.data_sheet("Users").table()
            # openpyxlではキャッシュ付き数式を作れないため、数式本体と
            # 保存済み値の組み合わせをそれぞれ明示して分岐を確認する。
            table._worksheet["B2"] = "=A2*2"
            with (
                patch.object(
                    excel, "_cached_range", return_value=([("id", "total"), (1, 2)], False)
                ),
                patch.object(excel, "_read_range_with_com") as read_with_com,
            ):
                result = table.read()

        assert result.read_rows() == [{"id": "1", "total": "2"}]
        read_with_com.assert_not_called()

    def test_uncalculated_formula_automatically_reads_only_table_ref_with_com(
        self, tmp_path
    ) -> None:
        path = tmp_path / "uncalculated.xlsx"
        with Excel(path) as excel:
            excel.create_data_sheet("Users").create_table(
                "Users", Table(["id", "total"], [{"id": 1, "total": "=A2*2"}])
            )

        with Excel(path) as excel:
            table = excel.data_sheet("Users").table()
            with patch.object(
                excel,
                "_read_range_with_com",
                return_value=[("id", "total"), (1, 2)],
            ) as read_with_com:
                result = table.read()

        assert result.read_rows() == [{"id": "1", "total": "2"}]
        read_with_com.assert_called_once_with("PY_Users", 1, 1, 2, 2)

    def test_force_com_reads_only_table_ref(self, tmp_path) -> None:
        path = tmp_path / "forced.xlsx"
        with Excel(path) as excel:
            table = excel.create_data_sheet("Users").create_table(
                "Users", Table(["id"], [{"id": 1}])
            )
            with patch.object(
                excel, "_read_range_with_com", return_value=[("id",), (2,)]
            ) as read_with_com:
                result = table.read(force_com=True)

        assert result.read_rows() == [{"id": "2"}]
        read_with_com.assert_called_once_with("PY_Users", 1, 1, 1, 2)

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
            assert sheet.read_range("A1:B2").read_rows() == [{"name": "sales", "value": 10}]
            assert sheet.get_used_range() == ("A1", "B2")
