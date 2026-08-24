"""個別例外クラスの型とメッセージを確認する。"""

import warnings

import pytest

import comken.exceptions
from comken.exceptions import (
    ColumnNotFoundError,
    ComkenError,
    ConfigError,
    ConfigFileNotFoundError,
    ConfigMappingEmptyValueError,
    ConfigSectionNotFoundError,
    CSVError,
    CSVFileNotFoundError,
    EmptyHeaderCellError,
    EncodingDetectionError,
    ExcelColumnNotFoundError,
    ExcelError,
    ExcelFileNotFoundError,
    ExcelHeadersTooFewError,
    FileFormatMismatchError,
    KeyColumnNotFoundError,
    MacroError,
    SheetNotFoundError,
)
from comken.exceptions.warning import _warn_coerce


def test_excel_formula_error_is_not_exposed() -> None:
    assert not hasattr(comken.exceptions, "ExcelFormulaError")


def test_original_libs_error_is_not_exposed() -> None:
    assert not hasattr(comken.exceptions, "OriginalLibsError")


def test_all_declared_names_are_resolvable() -> None:
    """`__all__` のすべての名前がモジュール属性として取得できる。"""
    missing = [name for name in comken.exceptions.__all__ if not hasattr(comken.exceptions, name)]
    assert missing == [], f"`__all__` に未定義の名前があります: {missing}"


@pytest.mark.parametrize(
    ("error", "base", "message"),
    [
        (ExcelFileNotFoundError("book.xlsx"), ExcelError, "book.xlsx"),
        (SheetNotFoundError("集計", ["Sheet1"]), ExcelError, "集計"),
        (MacroError("Module1.Run", "失敗"), ExcelError, "Module1.Run"),
        (EmptyHeaderCellError([2]), ExcelError, "列番号: [2]"),
        (ExcelHeadersTooFewError(2, 3), ExcelError, "2列"),
        (FileFormatMismatchError(".csv"), ExcelError, ".csv"),
        (EncodingDetectionError("data.csv"), CSVError, "data.csv"),
        (CSVFileNotFoundError("data.csv"), CSVError, "data.csv"),
        (ExcelColumnNotFoundError(["金額"]), ColumnNotFoundError, "金額"),
        (KeyColumnNotFoundError("ID", ["名前"]), ColumnNotFoundError, "ID"),
        (ConfigFileNotFoundError("config.ini"), ConfigError, "config.ini"),
        (ConfigSectionNotFoundError("FILES", ["LOG"]), ConfigError, "[FILES]"),
        (
            ConfigMappingEmptyValueError("config.ini", "[T_MAPPING]", ["部署名"]),
            ConfigError,
            "[T_MAPPING]",
        ),
    ],
)
def test_individual_error_type_and_message(
    error: ComkenError,
    base: type[ComkenError],
    message: str,
) -> None:
    """各失敗が個別型を持ち、値を含むメッセージを自分で組み立てる。"""
    with pytest.raises(type(error)) as caught:
        raise error
    assert isinstance(caught.value, base)
    assert isinstance(caught.value, ComkenError)
    assert message in str(caught.value)


class TestWarnCoerce:
    """_warn_coerce のテスト。"""

    def test_none_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="None"):
            _warn_coerce(None, str, "sheet_name")

    def test_wrong_type_warns_and_converts(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = _warn_coerce(1, str, "sheet_name")
        assert result == "1"
        assert len(caught) == 1
        assert issubclass(caught[0].category, UserWarning)

    def test_correct_type_no_warning(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = _warn_coerce("ok", str, "sheet_name")
        assert result == "ok"
        assert len(caught) == 0
