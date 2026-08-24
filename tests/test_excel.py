"""現行のExcel API（Excel / Sheet / ExcelTable）の契約テスト。"""

import pytest

from comken.core.table import Table
from comken.exceptions import (
    DataSheetAccessError,
    ExcelFileNotFoundError,
    ExcelReadOnlyOperationError,
    InvalidTableNameError,
    InvalidTableOperationError,
    SheetAlreadyExistsError,
    SheetNameError,
    TableNotOpenError,
    UnsupportedFileSuffixError,
)
from comken.toolbox.excel import Excel


def test_excel_creates_and_reads_python_table(tmp_path) -> None:
    path = tmp_path / "book.xlsx"
    with Excel(path) as excel:
        sheet = excel.create_data_sheet("顧客")
        sheet.create_table("顧客", Table(["ID", "名前"], [{"ID": "001", "名前": "山田"}]))
    with Excel(path, read_only=True) as excel:
        assert excel.data_sheet("顧客").table().read() == [{"ID": "001", "名前": "山田"}]


def test_excel_replaces_table_without_saving_until_context_exit(tmp_path) -> None:
    path = tmp_path / "book.xlsx"
    with Excel(path) as excel:
        excel.create_data_sheet("顧客").create_table("顧客", Table(["ID"], [{"ID": "001"}]))
    with Excel(path) as excel:
        table = excel.data_sheet("顧客").table()
        table.replace([{"ID": "002"}])
        assert table.read() == [{"ID": "002"}]
    with Excel(path, read_only=True) as excel:
        assert excel.data_sheet("顧客").table().read() == [{"ID": "002"}]


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
    path = tmp_path / "missing.xlsx"
    with pytest.raises(ExcelFileNotFoundError), Excel(path, read_only=True):
        pass
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
    with Excel(path, read_only=True) as excel, pytest.raises(ExcelReadOnlyOperationError):
        excel.create_sheet("別のシート")


def test_create_sheet_returns_sheet_that_supports_layout_api(tmp_path) -> None:
    path = tmp_path / "book.xlsx"
    with Excel(path) as excel:
        sheet = excel.create_sheet("集計")
        # 表示用シートでは table() は DataSheetAccessError
        with pytest.raises(DataSheetAccessError):
            sheet.table()


def test_set_border_uses_thin_by_default(tmp_path) -> None:
    """set_border() は style を省略すると thin が使われる。"""
    import inspect

    from comken.toolbox.excel.sheet import Sheet

    path = tmp_path / "book.xlsx"
    with Excel(path) as excel:
        sheet = excel.create_sheet("集計")
        sheet.write_value("A1", "x")
        sheet.set_border("A1")
    with Excel(path, read_only=True) as excel:
        cell = excel.sheet("集計")._worksheet["A1"]
        assert cell.border.left.style == "thin"
        # openpyxl は 8 桁の ARGB 形式で色を保存する（先頭 2 桁はアルファチャンネル）
        assert cell.border.left.color.value == "00000000"
    # 型定義の Literal として受け付ける値の一覧（実行時の網羅チェック）
    sig = inspect.signature(Sheet.set_border)
    if sig.parameters["style"].default != "thin":
        pytest.fail(f"style 既定値が 'thin' ではない: {sig.parameters['style'].default!r}")
    if sig.parameters["color"].default != "000000":
        pytest.fail(f"color 既定値が '000000' ではない: {sig.parameters['color'].default!r}")


def test_set_border_accepts_style_and_strips_hash(tmp_path) -> None:
    """style / color を指定でき、color の '#' は落ちる。"""
    path = tmp_path / "book.xlsx"
    with Excel(path) as excel:
        sheet = excel.create_sheet("集計")
        sheet.write_value("A1", "x")
        sheet.set_border("A1", style="thick", color="#FF0000")
    with Excel(path, read_only=True) as excel:
        cell = excel.sheet("集計")._worksheet["A1"]
        assert cell.border.left.style == "thick"
        assert cell.border.right.style == "thick"
        assert cell.border.top.style == "thick"
        assert cell.border.bottom.style == "thick"
        # openpyxl は 8 桁の ARGB 形式で色を保存する（先頭 2 桁はアルファチャンネル）
        assert cell.border.left.color.value == "00FF0000"


def test_set_border_rejects_unknown_keyword() -> None:
    """未知のキーワードは Python の呼び出し時点で TypeError。"""
    import inspect

    from comken.toolbox.excel.sheet import Sheet

    sig = inspect.signature(Sheet.set_border)
    # set_border() は style / color しか受け付けないため、
    # 未知のキーワードを bind しようとすると TypeError になる。
    with pytest.raises(TypeError):
        sig.bind("A1", thickness=2)


def test_openpyxl_side_rejects_unknown_style_with_clear_message() -> None:
    """openpyxl の Side は無効な style を ValueError にして、有効値の一覧を返す。

    comken の Sheet.set_border() は Literal 型でビルド時に不正値を防ぐので、
    openpyxl 側の例外メッセージはここで直接確認する。
    """
    from openpyxl.styles import Side

    with pytest.raises(ValueError, match="Value must be one of"):
        Side(style="thinn", color="000000")


def test_excel_outside_with_block_raises_table_not_open_error(tmp_path) -> None:
    path = tmp_path / "book.xlsx"
    excel = Excel(path)
    with pytest.raises(TableNotOpenError, match="Excel"):
        excel.list_data_sheets()
    with pytest.raises(TableNotOpenError, match="Excel"):
        excel.data_sheet("顧客")
    with pytest.raises(TableNotOpenError, match="Excel"):
        excel.create_sheet("集計")
    with pytest.raises(TableNotOpenError, match="Excel"):
        excel.save()


class TestCreateTableNameValidation:
    """``Sheet.create_table`` は Excel が受け付けない名前を ``InvalidTableNameError`` で止める。"""

    @pytest.mark.parametrize(
        "invalid_name",
        [
            pytest.param("", id="empty"),
            pytest.param("結 果", id="contains-half-width-space"),
            pytest.param("結　果", id="contains-full-width-space"),
            pytest.param("1結果", id="starts-with-digit"),
            pytest.param("A1", id="cell-reference-A1"),
            pytest.param("R1C1", id="cell-reference-R1C1"),
            pytest.param("Bad/Name", id="forbidden-slash"),
            pytest.param("Bad*Name", id="forbidden-asterisk"),
            pytest.param("Bad[Name", id="forbidden-bracket"),
            pytest.param("Bad]Name", id="forbidden-close-bracket"),
        ],
    )
    def test_invalid_names_raise(self, tmp_path, invalid_name: str) -> None:
        path = tmp_path / "book.xlsx"
        with Excel(path) as excel, pytest.raises(InvalidTableNameError):
            excel.create_data_sheet("S").create_table(invalid_name, Table(["a"], [{"a": "1"}]))

    def test_valid_japanese_name_is_accepted(self, tmp_path) -> None:
        path = tmp_path / "book.xlsx"
        with Excel(path) as excel:
            table = excel.create_data_sheet("S").create_table("顧客", Table(["ID"], [{"ID": "1"}]))
            rows = table.read()
        assert rows == [{"ID": "1"}]
