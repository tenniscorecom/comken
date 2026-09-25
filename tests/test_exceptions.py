"""個別例外クラスの型とメッセージを確認する。"""

import warnings

import pytest

import comken.exceptions
from comken.exceptions import (
    ColumnNotFoundError,
    ComkenError,
    ComkenFileNotFoundError,
    ConfigError,
    ConfigMappingEmptyValueError,
    ConfigSectionNotFoundError,
    CSVError,
    ExcelColumnNotFoundError,
    ExcelError,
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
        (
            ComkenFileNotFoundError(
                "Excel ファイル",
                "book.xlsx",
                "パスが正しいか、ファイルが存在するかを確認してください。",
            ),
            ComkenError,
            "book.xlsx",
        ),
        (SheetNotFoundError("集計", ["Sheet1"]), ExcelError, "集計"),
        (
            ExcelError("VBA マクロの実行に失敗しました: Module1.Run\n（詳細: 失敗）"),
            ExcelError,
            "Module1.Run",
        ),
        (
            ExcelError(
                "ヘッダー行に空のセルがあります。列番号: [2]\n"
                "Excelの1行目（ヘッダー行）を確認してください。"
            ),
            ExcelError,
            "列番号: [2]",
        ),
        (
            ExcelError(
                "headers の列数（2列）がシートの列数（3列）より少ないため、"
                "はみ出した列のデータが失われます。\n"
                "headers にすべての列名を指定してください。"
            ),
            ExcelError,
            "2列",
        ),
        (
            ExcelError(
                "保存先の拡張子（.csv）が元ファイルの形式と一致しません。\n"
                "形式を変換して保存する場合は file_format 引数で FileFormat 定数を"
                "指定してください。（例: file_format=FileFormat.CSV）"
            ),
            ExcelError,
            ".csv",
        ),
        (
            CSVError(
                "文字コードを判定できませんでした"
                "（UTF-8 / CP932 のどちらでも読めません）: data.csv\n"
                "encoding 引数で明示してください。"
            ),
            CSVError,
            "data.csv",
        ),
        (ComkenFileNotFoundError("CSV ファイル", "data.csv"), ComkenError, "data.csv"),
        (ExcelColumnNotFoundError(["金額"]), ColumnNotFoundError, "金額"),
        (
            ColumnNotFoundError("キー列が見つかりません: ID\n存在する列: 名前"),
            ColumnNotFoundError,
            "ID",
        ),
        (
            ComkenFileNotFoundError(
                "config.ini",
                "config.ini",
                "同じ場所に config.ini.example があるか確認してください。"
                "あれば、もう一度実行するだけで config.ini が作られます。",
            ),
            ComkenError,
            "config.ini",
        ),
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
