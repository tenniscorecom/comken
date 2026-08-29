"""``Excel.convert_range_to_table`` の契約テスト。

openpyxl 経路だけで完結する。``engine='com'`` 経路は ``NotImplementedError``
を確認する 1 本だけ用意する（COM の本体テストは test_excel_com_engine.py 側）。
"""

from __future__ import annotations

import pytest

from comken.exceptions import (
    DuplicateHeaderCellError,
    EmptyHeaderCellError,
    InvalidTableInputError,
    InvalidTableNameError,
    TableAlreadyExistsError,
)
from comken.toolbox.excel import Excel
from comken.toolbox.excel.workbook import ExcelTable


def _write_simple_table(sheet, *, rows: int = 3) -> None:
    """1 行目を見出し、2 行目以降にデータが入っている状態を作る。"""
    sheet.write_range("A1:C1", [["ID", "名前", "備考"]])
    for index in range(2, rows + 2):
        sheet.write_value(f"A{index}", str(index - 1))
        sheet.write_value(f"B{index}", f"ユーザー{index - 1}")
        sheet.write_value(f"C{index}", "OK")


class TestConvertRangeToTableSuccess:
    """正常系: 単純な表（結合なし、空行なし、重複なし）をテーブル化できる。"""

    def test_creates_table_from_existing_cells(self, tmp_path) -> None:
        path = tmp_path / "book.xlsx"
        with Excel(path) as excel:
            sheet = excel.create_sheet("案件一覧")
            _write_simple_table(sheet, rows=3)
            excel.convert_range_to_table("案件一覧", range="A1:C4", table_name="案件")
            tables = list(excel._workbook["案件一覧"].tables)
            assert tables == ["案件"]

    def test_returns_excel_table_instance(self, tmp_path) -> None:
        """戻り値が ``ExcelTable`` インスタンスで ``read()`` が動くこと。"""
        path = tmp_path / "book.xlsx"
        with Excel(path) as excel:
            sheet = excel.create_sheet("案件一覧")
            _write_simple_table(sheet)
            table = excel.convert_range_to_table("案件一覧", range="A1:C4", table_name="案件")
            assert isinstance(table, ExcelTable)
            assert table.read() == [
                {"ID": "1", "名前": "ユーザー1", "備考": "OK"},
                {"ID": "2", "名前": "ユーザー2", "備考": "OK"},
                {"ID": "3", "名前": "ユーザー3", "備考": "OK"},
            ]

    def test_explicit_header_row_is_used(self, tmp_path) -> None:
        """``header_row`` を明示したとき、A2 ルールではなくその行を見出しとして使う。"""
        path = tmp_path / "book.xlsx"
        with Excel(path) as excel:
            sheet = excel.create_sheet("案件一覧")
            # 1 行目には結合（タイトル）を入れ、2 行目が空、3 行目から見出し
            sheet.write_value("A1", "案件一覧（タイトル）")
            sheet.merge_cells("A1:C1")
            sheet.write_range("A3:C3", [["ID", "名前", "備考"]])
            for index in range(4, 7):
                sheet.write_value(f"A{index}", str(index - 3))
                sheet.write_value(f"B{index}", f"ユーザー{index - 3}")
                sheet.write_value(f"C{index}", "OK")
            # header_row=3 を明示するので、結合があってもそれを見出しとして扱う。
            excel.convert_range_to_table(
                "案件一覧",
                range="A1:C6",
                table_name="案件",
                header_row=3,
            )
            assert "案件" in excel._workbook["案件一覧"].tables


class TestA2Rule:
    """A2 ルール: 先頭行に結合セルがあるとき次行を見出しとみなす。"""

    def test_first_row_merged_makes_second_row_header(self, tmp_path) -> None:
        """1 行目にタイトル結合、2 行目から見出し、3 行目以降にデータ。"""
        path = tmp_path / "book.xlsx"
        with Excel(path) as excel:
            sheet = excel.create_sheet("案件一覧")
            # 1 行目: タイトル（結合）
            sheet.write_value("A1", "案件一覧")
            sheet.merge_cells("A1:C1")
            # 2 行目: 見出し
            sheet.write_range("A2:C2", [["ID", "名前", "備考"]])
            for index in range(3, 6):
                sheet.write_value(f"A{index}", str(index - 2))
                sheet.write_value(f"B{index}", f"ユーザー{index - 2}")
                sheet.write_value(f"C{index}", "OK")
            # header_row を指定しないので A2 が発火して 2 行目を見出しにする
            excel.convert_range_to_table("案件一覧", range="A1:C5", table_name="案件")
            tables = list(excel._workbook["案件一覧"].tables)
            assert tables == ["案件"]

    def test_no_merged_first_row_uses_first_row_as_header(self, tmp_path) -> None:
        """先頭行に結合が無い場合は先頭行を見出しとして使う（A2 ルール不発火）。"""
        path = tmp_path / "book.xlsx"
        with Excel(path) as excel:
            sheet = excel.create_sheet("案件一覧")
            _write_simple_table(sheet)
            excel.convert_range_to_table("案件一覧", range="A1:C4", table_name="案件")
            tables = list(excel._workbook["案件一覧"].tables)
            assert tables == ["案件"]


class TestConvertRangeToTableErrors:
    """異常系: 安全性判定に違反した場合、対応する既存例外が上がる。"""

    def test_empty_header_cell_raises(self, tmp_path) -> None:
        """見出し行のセルが空なら ``EmptyHeaderCellError``。"""
        path = tmp_path / "book.xlsx"
        with Excel(path) as excel:
            sheet = excel.create_sheet("案件一覧")
            sheet.write_range("A1:C1", [["ID", "", "備考"]])
            sheet.write_value("A2", "1")
            sheet.write_value("B2", "A")
            sheet.write_value("C2", "OK")
            with pytest.raises(EmptyHeaderCellError):
                excel.convert_range_to_table("案件一覧", range="A1:C2", table_name="案件")

    def test_merged_cell_inside_range_raises(self, tmp_path) -> None:
        """見出し行より下にある結合は ``InvalidTableInputError``。"""
        path = tmp_path / "book.xlsx"
        with Excel(path) as excel:
            sheet = excel.create_sheet("案件一覧")
            sheet.write_range("A1:C1", [["ID", "名前", "備考"]])
            sheet.write_value("A2", "1")
            sheet.write_value("B2", "A")
            sheet.merge_cells("B3:C3")
            sheet.write_value("A3", "2")
            with pytest.raises(InvalidTableInputError, match="結合セル"):
                excel.convert_range_to_table("案件一覧", range="A1:C3", table_name="案件")

    def test_blank_row_in_data_raises(self, tmp_path) -> None:
        """データ途中の空行は ``InvalidTableInputError``（該当行番号を含む）。"""
        path = tmp_path / "book.xlsx"
        with Excel(path) as excel:
            sheet = excel.create_sheet("案件一覧")
            sheet.write_range("A1:C1", [["ID", "名前", "備考"]])
            sheet.write_value("A2", "1")
            sheet.write_value("B2", "A")
            sheet.write_value("C2", "OK")
            # 3 行目は空
            sheet.write_value("A4", "2")
            sheet.write_value("B4", "B")
            sheet.write_value("C4", "OK")
            with pytest.raises(InvalidTableInputError, match="空行") as exc_info:
                excel.convert_range_to_table("案件一覧", range="A1:C4", table_name="案件")
            # 行番号がメッセージに含まれること
            assert "3" in str(exc_info.value)

    def test_duplicate_headers_raise(self, tmp_path) -> None:
        """見出しの重複は ``DuplicateHeaderCellError``。"""
        path = tmp_path / "book.xlsx"
        with Excel(path) as excel:
            sheet = excel.create_sheet("案件一覧")
            sheet.write_range("A1:C1", [["ID", "ID", "備考"]])
            sheet.write_value("A2", "1")
            sheet.write_value("B2", "A")
            sheet.write_value("C2", "OK")
            with pytest.raises(DuplicateHeaderCellError):
                excel.convert_range_to_table("案件一覧", range="A1:C2", table_name="案件")

    @pytest.mark.parametrize(
        "invalid_name",
        [
            pytest.param("", id="empty"),
            pytest.param("1結果", id="starts-with-digit"),
            pytest.param("A1", id="cell-reference"),
            pytest.param("Bad/Name", id="forbidden-slash"),
            pytest.param("結 果", id="contains-half-width-space"),
        ],
    )
    def test_invalid_table_names_raise(self, tmp_path, invalid_name: str) -> None:
        """Excel のテーブル命名規則違反は ``InvalidTableNameError``。"""
        path = tmp_path / "book.xlsx"
        with Excel(path) as excel:
            sheet = excel.create_sheet("案件一覧")
            _write_simple_table(sheet)
            with pytest.raises(InvalidTableNameError):
                excel.convert_range_to_table("案件一覧", range="A1:C4", table_name=invalid_name)

    def test_duplicate_table_name_raises(self, tmp_path) -> None:
        """同じテーブル名が既に存在するときは ``TableAlreadyExistsError``。"""
        path = tmp_path / "book.xlsx"
        with Excel(path) as excel:
            sheet = excel.create_sheet("案件一覧")
            _write_simple_table(sheet)
            excel.convert_range_to_table("案件一覧", range="A1:C4", table_name="案件")
            sheet.write_range("E1:G1", [["ID", "名前", "備考"]])
            sheet.write_value("E2", "1")
            sheet.write_value("F2", "A")
            sheet.write_value("G2", "OK")
            with pytest.raises(TableAlreadyExistsError):
                excel.convert_range_to_table("案件一覧", range="E1:G2", table_name="案件")

    def test_range_outside_dimensions_raises(self, tmp_path) -> None:
        """シートの使用範囲外を指定すると ``InvalidTableInputError``。"""
        path = tmp_path / "book.xlsx"
        with Excel(path) as excel:
            sheet = excel.create_sheet("案件一覧")
            _write_simple_table(sheet)
            # E 列にはデータが無いので A1:F4 のような範囲外指定はエラー
            with pytest.raises(InvalidTableInputError):
                excel.convert_range_to_table("案件一覧", range="A1:F4", table_name="案件")


class TestConvertRangeToTableComEngine:
    """``engine='com'`` で ``convert_range_to_table`` を呼ぶと ``NotImplementedError``。"""

    def test_com_engine_raises_not_implemented(self, tmp_path) -> None:
        from unittest.mock import MagicMock

        from comken.toolbox.excel import Excel as ExcelCls

        path = tmp_path / "book.xlsx"
        path.write_bytes(b"")
        fake_com = MagicMock()
        fake_com.__enter__.return_value = fake_com
        fake_com.__exit__.return_value = False
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "comken.toolbox.windows.handler.ExcelCOMHandler",
                MagicMock(return_value=fake_com),
            )
            with (
                ExcelCls(path, engine="com", local_copy=False) as excel,
                pytest.raises(NotImplementedError, match="openpyxl で開いたブック"),
            ):
                excel.convert_range_to_table("案件一覧", range="A1:C4", table_name="案件")
