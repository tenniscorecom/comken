"""個別例外クラスの型とメッセージを確認する。"""

import warnings

import pytest

from comken.exceptions import (
    ColumnNotFoundError,
    ConfigError,
    ConfigFileNotFoundError,
    ConfigSectionNotFoundError,
    CsvColumnNotFoundError,
    CsvError,
    CsvHeadersTooFewError,
    CsvNoDataRowsError,
    EmptyHeaderCellError,
    EncodingDetectionError,
    ExcelColumnNotFoundError,
    ExcelError,
    ExcelFileNotFoundError,
    ExcelFormulaError,
    ExcelHeadersTooFewError,
    FileFormatMismatchError,
    KeyColumnNotFoundError,
    MacroError,
    OriginalLibsError,
    RowTransferError,
    SheetNotFoundError,
    _warn_coerce,
)


@pytest.mark.parametrize(
    ("error", "base", "message"),
    [
        (ExcelFileNotFoundError("book.xlsx"), ExcelError, "book.xlsx"),
        (
            ExcelFormulaError([("集計", "$E$1", "#REF!")]),
            ExcelError,
            "集計!$E$1",
        ),
        (SheetNotFoundError("集計", ["Sheet1"]), ExcelError, "集計"),
        (MacroError("Module1.Run", "失敗"), ExcelError, "Module1.Run"),
        (RowTransferError(3, "不正値"), ExcelError, "3行目"),
        (EmptyHeaderCellError([2]), ExcelError, "列番号: [2]"),
        (ExcelHeadersTooFewError(2, 3), ExcelError, "2列"),
        (FileFormatMismatchError(".csv"), ExcelError, ".csv"),
        (EncodingDetectionError("data.csv"), CsvError, "data.csv"),
        (CsvHeadersTooFewError(2, "data.csv"), CsvError, "2列"),
        (CsvNoDataRowsError("data.csv"), CsvError, "ヘッダー行の下"),
        (ExcelColumnNotFoundError(["金額"]), ColumnNotFoundError, "金額"),
        (
            CsvColumnNotFoundError(["金額"], ["日付"]),
            ColumnNotFoundError,
            "存在する列: 日付",
        ),
        (KeyColumnNotFoundError("ID", ["名前"]), ColumnNotFoundError, "ID"),
        (ConfigFileNotFoundError("config.ini"), ConfigError, "config.ini"),
        (ConfigSectionNotFoundError("FILES", ["LOG"]), ConfigError, "[FILES]"),
    ],
)
def test_individual_error_type_and_message(
    error: OriginalLibsError,
    base: type[OriginalLibsError],
    message: str,
) -> None:
    """各失敗が個別型を持ち、値を含むメッセージを自分で組み立てる。"""
    with pytest.raises(type(error)) as caught:
        raise error
    assert isinstance(caught.value, base)
    assert isinstance(caught.value, OriginalLibsError)
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
