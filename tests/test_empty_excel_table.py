"""ExcelTable.read() の空テーブル検出と例外メッセージを確認する。"""

from unittest.mock import patch

import pytest

from comken.core.table import Table
from comken.exceptions import EmptyExcelTableError, EmptyHeaderCellError, ExcelError
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
        assert table.read().read() == [{"id": "1", "name": "A"}]
        # ref は A1:B2（ヘッダ + 1 行）に収まる。assert 経路を通っていないことを
        # 副次的に確かめるため、openpyxl の ref 文字列で ref の形を見る
        excel_table = excel.data_sheet("Users").table()._worksheet.tables["PY_T_Users"]
        assert excel_table.ref == "A1:B2"


def test_replace_with_empty_rows_clears_last_cell_beyond_new_ref(tmp_path) -> None:
    """``replace()`` で行を 0 件にしたとき、旧テーブルの末尾セルをクリアする。"""
    path = tmp_path / "shrink.xlsx"
    with Excel(path) as excel:
        table = excel.create_data_sheet("Users").create_table(
            "Users",
            Table(["id", "name"], [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]),
        )
        # 旧 ref は A1:B3。 0 行のテーブルで置換すると ``_clear_removed_cells`` が
        # 旧 max_row 行の値を空にする。新 ref は A1:A2（A 列のみ、ヘッダ + 1 行）。
        table.replace(Table(["id"], []))
        assert table._worksheet["B3"].value is None  # 旧データ末尾の name 列
        assert table._worksheet["A3"].value is None  # 旧データ末尾の id 列（表外）
        # 新 ref は「先頭 + 末尾1行」に縮んでいる
        excel_table = table._worksheet.tables["PY_T_Users"]
        assert excel_table.ref == "A1:A2"


def test_replace_with_empty_rows_keeps_existing_headers(tmp_path) -> None:
    """``replace([])`` で空リストを渡したとき、既存ヘッダが維持される。"""
    path = tmp_path / "keep_headers.xlsx"
    with Excel(path) as excel:
        table = excel.create_data_sheet("Users").create_table(
            "Users",
            Table(["id", "name"], [{"id": 1, "name": "A"}]),
        )
        # 引数が ``list`` のときもヘルパー経由の ``_table_boundaries`` を通り、
        # ``assert`` 経路を踏まずに ref が更新されることを確認する
        table.replace([])
        assert table.read().columns == ["id", "name"]
        assert table.read().read() == []
