"""ExcelTable.read() の空テーブル検出と例外メッセージを確認する。"""

from unittest.mock import patch

import pytest

from comken.core.table import Table
from comken.exceptions import (
    EmptyExcelTableError,
    EmptyHeaderCellError,
    ExcelError,
    InvalidTableOperationError,
    TableColumnMismatchError,
)
from comken.toolbox.excel import Excel


def test_read_raises_when_range_read_returns_no_rows(tmp_path) -> None:
    """COM 等でテーブル範囲の読み取りが 0 行のときに例外を投げる。"""
    path = tmp_path / "no_data.xlsx"
    with Excel(path) as excel:
        table = excel.create_data_sheet("Users").create_table("Users", Table(["id"], [{"id": 1}]))
        # 数式を入れて COM 経路を強制する
        table._worksheet["B2"] = "=A2*2"

    with Excel(path) as excel:
        table = excel.data_sheet("Users").table()
        # COM 読み込みを空結果にして rows が空になるシナリオを作る
        with (
            patch.object(excel, "_read_range_with_com", return_value=[]),
            pytest.raises(EmptyExcelTableError) as exc_info,
        ):
            table.read(force_com=True)

        assert exc_info.value.sheet_name == "PY_Users"
        assert "テーブル範囲を読み取れませんでした" in str(exc_info.value)


def test_read_uses_header_error_when_header_row_is_empty(tmp_path) -> None:
    """読み取り結果にヘッダ行があれば、空見出しとして検証する。"""
    path = tmp_path / "no_header.xlsx"
    with Excel(path) as excel:
        table = excel.create_data_sheet("Users").create_table("Users", Table(["id"], [{"id": 1}]))

        with (
            patch.object(excel, "_read_range_with_com", return_value=[(None,)]),
            pytest.raises(EmptyHeaderCellError) as exc_info,
        ):
            table.read(force_com=True)

    assert "列番号: [1]" in str(exc_info.value)


def test_empty_excel_table_error_is_a_subclass_of_excel_error() -> None:
    """EmptyExcelTableError が ExcelError の派生であることを確認する。"""
    assert issubclass(EmptyExcelTableError, ExcelError)


def test_replace_on_empty_table_adds_first_data_row(tmp_path) -> None:
    """データ行が 0 個の既存テーブルへ ``replace()`` しても例外が出ず、ref が縮む。"""
    path = tmp_path / "empty.xlsx"
    with Excel(path) as excel:
        table = excel.create_data_sheet("Users").create_table("Users", Table(["id", "name"], []))
        assert table.count() == 0
        # 既存テストでカバー済みの「後から 0 行で置換」とは別に、最初に 0 行の
        # テーブルへ ``replace()`` する場合の経路を検証する。 ``new_max_row`` が
        # ``min_row + max(len(rows), 1)`` で 1 行分に丸められる分岐を通る。
        table.replace(Table(["id", "name"], [{"id": 1, "name": "A"}]))
        assert table.read() == [{"id": "1", "name": "A"}]
        # ref は A1:B2（ヘッダ + 1 行）に収まる。assert 経路を通っていないことを
        # 副次的に確かめるため、openpyxl の ref 文字列で ref の形を見る
        excel_table = excel.data_sheet("Users").table()._worksheet.tables["PY_T_Users"]
        assert excel_table.ref == "A1:B2"


def test_replace_with_empty_rows_raises_when_omitting_non_formula_column(
    tmp_path,
) -> None:
    """``replace()`` で 0 行にしたとき、非数式列を省くと ``TableColumnMismatchError``。"""
    path = tmp_path / "shrink.xlsx"
    with Excel(path) as excel:
        table = excel.create_data_sheet("Users").create_table(
            "Users",
            Table(["id", "name"], [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]),
        )
        # 旧 ref は A1:B3。非数式列「name」を省いて 0 行で置換しようとすると
        # データ欠落を防ぐために例外になる。
        with pytest.raises(TableColumnMismatchError) as exc_info:
            table.replace(Table(["id"], []))
        assert "name" in str(exc_info.value)
        # 既存データはそのまま残っている
        assert table._worksheet["A2"].value == 1
        assert table._worksheet["B2"].value == "A"
        assert table._worksheet["A3"].value == 2
        assert table._worksheet["B3"].value == "B"


def test_replace_with_empty_list_raises(tmp_path) -> None:
    """``replace([])`` で空リストを渡したときは列無しの Table として例外。"""
    path = tmp_path / "keep_headers.xlsx"
    with Excel(path) as excel:
        table = excel.create_data_sheet("Users").create_table(
            "Users",
            Table(["id", "name"], [{"id": 1, "name": "A"}]),
        )
        with pytest.raises(InvalidTableOperationError) as exc_info:
            table.replace([])
        assert "列のないTable" in str(exc_info.value)
        # 既存ヘッダとデータはそのまま残っている
        assert table._worksheet["A1"].value == "id"
        assert table._worksheet["B1"].value == "name"
        assert table._worksheet["A2"].value == 1
        assert table._worksheet["B2"].value == "A"
