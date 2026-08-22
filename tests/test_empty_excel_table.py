"""ExcelTable.read() の空テーブル検出と例外メッセージを確認する。"""

from unittest.mock import patch

import pytest

from comken.core.table import Table
from comken.exceptions import EmptyExcelTableError, ExcelError
from comken.toolbox.excel import Excel


def test_read_raises_when_table_has_no_data_rows(tmp_path) -> None:
    """ref 範囲があるが読み込み結果が空のときに例外を投げる。"""
    path = tmp_path / "no_data.xlsx"
    with Excel(path) as excel:
        table = excel.create_data_sheet("Users").create_table(
            "Users", Table(["id"], [{"id": 1}])
        )
        # 数式を入れて COM 経路を強制する
        table._worksheet["B2"] = "=A2*2"

    with Excel(path) as excel:
        table = excel.data_sheet("Users").table()
        # COM 読み込みを空結果にして rows が空になるシナリオを作る
        with patch.object(excel, "_read_range_with_com", return_value=[]):
            with pytest.raises(EmptyExcelTableError) as exc_info:
                table.read(force_com=True)

        assert exc_info.value.sheet_name == "PY_Users"
        assert "データがありません" in str(exc_info.value)


def test_read_raises_when_header_row_is_empty(tmp_path) -> None:
    """ref 範囲があるがヘッダセルが全て空のときに例外を投げる。"""
    path = tmp_path / "no_header.xlsx"
    with Excel(path) as excel:
        excel.create_data_sheet("Users").create_table(
            "Users", Table(["id"], [{"id": 1}])
        )
        # ヘッダ行を空にする
        table = excel.data_sheet("Users").table()
        table._worksheet["A1"] = None
        table._excel._mark_dirty()

    with Excel(path) as excel:
        read_table = excel.data_sheet("Users").table()

        with pytest.raises(EmptyExcelTableError) as exc_info:
            read_table.read()

        assert exc_info.value.sheet_name == "PY_Users"
        assert "ヘッダ行が空です" in str(exc_info.value)


def test_empty_excel_table_error_is_a_subclass_of_excel_error() -> None:
    """EmptyExcelTableError が ExcelError の派生であることを確認する。"""
    assert issubclass(EmptyExcelTableError, ExcelError)
