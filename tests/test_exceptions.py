"""個別例外クラスの型とメッセージを確認する。"""

import warnings

import pytest

import comken.exceptions
from comken.exceptions import (
    ColumnNotFoundError,
    ComkenError,
    ComkenFileNotFoundError,
    ConfigError,
    CSVError,
    ExcelColumnNotFoundError,
    ExcelError,
    SalesforceError,
    SalesforceReportAccessDeniedError,
    SalesforceReportFormatError,
    SheetNotFoundError,
)
from comken.exceptions.tables import _coerce_to_str

# 複数のテストで使い回す長めの文字列は定数に置き、行長 100 を超えないようにする
_ACCESS_DENIED_DETAIL = "Analytics API 権限がありません"
_REPORT_ID = "00O000000000001"


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
        (ConfigError("[FILES] セクションがありません"), ConfigError, "[FILES]"),
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


class TestCoerceToStr:
    """_coerce_to_str のテスト。"""

    def test_none_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="None"):
            _coerce_to_str(None, "sheet_name")

    def test_wrong_type_warns_and_converts(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = _coerce_to_str(1, "sheet_name")
        assert result == "1"
        assert len(caught) == 1
        assert issubclass(caught[0].category, UserWarning)

    def test_correct_type_no_warning(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = _coerce_to_str("ok", "sheet_name")
        assert result == "ok"
        assert len(caught) == 0


class TestReportErrorSubclasses:
    """レポート形式の不一致とアクセス拒否は、専用の ``SalesforceError`` 子クラスとして
    送出される。利用側が型で分岐できるようにしつつ、``except SalesforceError`` の
    既存経路は壊さない契約になっていないといけない。
    """

    def test_format_error_is_salesforce_error_subclass(self) -> None:
        """``SalesforceReportFormatError`` は ``SalesforceError`` の子クラスで、
        既存の ``except SalesforceError`` でも捕捉できる。
        """
        exc = SalesforceReportFormatError("00O000000000001", "MULTI_BLOCK")
        assert isinstance(exc, SalesforceError)
        assert isinstance(exc, ComkenError)
        assert isinstance(exc, SalesforceReportFormatError)

    def test_format_error_attributes(self) -> None:
        """レポート ID と形式の短い理由は属性としても持っていて、プログラムから
        機械的に判定できる（メッセージ抽出に依存しない）。
        """
        exc = SalesforceReportFormatError("00O000000000001", "MULTI_BLOCK")
        assert exc.report_id == "00O000000000001"
        assert exc.report_format == "MULTI_BLOCK"

    def test_format_error_message_preserved(self) -> None:
        """メッセージ本文は旧 ``SalesforceError`` の文言と同じ。利用者ログや
        ``str(exc)`` ベースの既存分岐を壊さない。
        """
        exc = SalesforceReportFormatError("00O000000000001", "MULTI_BLOCK")
        message = str(exc)
        assert "MULTI_BLOCK" in message
        assert "00O000000000001" in message
        assert "TABULAR" in message
        assert "SUMMARY" in message
        assert "MATRIX" in message
        assert "対処" in message

    def test_format_error_raises_and_catches_by_type(self) -> None:
        """``raise`` して専用の型で ``except`` できる。"""
        with pytest.raises(SalesforceReportFormatError) as caught:
            raise SalesforceReportFormatError("00O000000000001", "MULTI_BLOCK")
        assert caught.value.report_id == "00O000000000001"
        assert caught.value.report_format == "MULTI_BLOCK"

    def test_format_error_catchable_by_salesforce_error(self) -> None:
        """``except SalesforceError`` でも後方互換で捉まる。"""
        with pytest.raises(SalesforceError):
            raise SalesforceReportFormatError("00O000000000001", "MULTI_BLOCK")

    def test_access_denied_error_is_salesforce_error_subclass(self) -> None:
        """``SalesforceReportAccessDeniedError`` は ``SalesforceError`` の子クラス。"""
        exc = SalesforceReportAccessDeniedError(_REPORT_ID, 403, _ACCESS_DENIED_DETAIL)
        assert isinstance(exc, SalesforceError)
        assert isinstance(exc, ComkenError)
        assert isinstance(exc, SalesforceReportAccessDeniedError)

    def test_access_denied_error_attributes(self) -> None:
        """レポート ID・HTTP ステータス・元の detail が属性として読める。
        メッセージ抽出ではなく機械的に判定できることを保証する。
        """
        exc = SalesforceReportAccessDeniedError(_REPORT_ID, 403, _ACCESS_DENIED_DETAIL)
        assert exc.report_id == _REPORT_ID
        assert exc.status_code == 403
        assert exc.detail == _ACCESS_DENIED_DETAIL

    def test_access_denied_error_message_preserved(self) -> None:
        """メッセージ本文は旧 ``SalesforceError`` の文言と同じ。"""
        exc = SalesforceReportAccessDeniedError(_REPORT_ID, 403, _ACCESS_DENIED_DETAIL)
        message = str(exc)
        assert "HTTP 403" in message
        assert _REPORT_ID in message
        assert _ACCESS_DENIED_DETAIL in message
        assert "API Enabled" in message
        assert "対処" in message

    def test_access_denied_error_raises_and_catches_by_type(self) -> None:
        """``raise`` して専用の型で ``except`` できる。"""
        with pytest.raises(SalesforceReportAccessDeniedError) as caught:
            raise SalesforceReportAccessDeniedError(_REPORT_ID, 403, _ACCESS_DENIED_DETAIL)
        assert caught.value.report_id == _REPORT_ID
        assert caught.value.status_code == 403
        assert caught.value.detail == _ACCESS_DENIED_DETAIL

    def test_access_denied_error_catchable_by_salesforce_error(self) -> None:
        """``except SalesforceError`` でも後方互換で捉まる。"""
        with pytest.raises(SalesforceError):
            raise SalesforceReportAccessDeniedError(_REPORT_ID, 403, _ACCESS_DENIED_DETAIL)

    def test_format_error_and_access_denied_are_distinct(self) -> None:
        """2 つの例外は別型。利用側が「形式」と「権限」を分けて扱える。"""
        assert not issubclass(SalesforceReportFormatError, SalesforceReportAccessDeniedError)
        assert not issubclass(SalesforceReportAccessDeniedError, SalesforceReportFormatError)
