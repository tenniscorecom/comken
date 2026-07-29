"""
exceptions.py — ライブラリ共通の例外クラス

すべての例外は OriginalLibsError を継承しているため、
まとめて補足したい場合は except OriginalLibsError で受けられる。

使い方:
    from comken.exceptions import SheetNotFoundError, ColumnNotFoundError

    try:
        with ExcelFile("data.xlsx") as f:
            rows = f.read_rows_as_dicts("存在しないシート")
    except SheetNotFoundError as e:
        print(e)  # → "シートが見つかりません: 存在しないシート ..."
"""

import warnings
from typing import Any, TypeVar

_T = TypeVar("_T")


class OriginalLibsError(Exception):
    """ライブラリ共通の基底例外。"""


class ExcelError(OriginalLibsError):
    """Excel 操作に関する例外の基底クラス。"""

    MSG_TRANSFER = (
        "Excel {row}行目の転記中にエラーが発生しました。"
        "該当行を確認してください。（詳細: {detail}）"
    )
    MSG_HEADER_NONE = (
        "ヘッダー行に空のセルがあります。列番号: {cols}\n"
        "Excelの1行目（ヘッダー行）を確認してください。"
    )
    MSG_HEADERS_TOO_FEW = (
        "headers の列数（{expected}列）がシートの列数（{actual}列）より少ないため、"
        "はみ出した列のデータが失われます。\n"
        "headers にすべての列名を指定してください。"
    )
    MSG_FORMAT_MISMATCH = (
        "保存先の拡張子（{suffix}）が元ファイルの形式と一致しません。\n"
        "形式を変換して保存する場合は file_format 引数で FileFormat 定数を"
        "指定してください。（例: file_format=FileFormat.CSV）"
    )
    MSG_FILE_NOT_FOUND = (
        "Excel ファイルが見つかりません: {path}\n"
        "パスが正しいか、ファイルが存在するかを確認してください。"
    )


class SheetNotFoundError(ExcelError):
    """指定したシートが存在しない場合。

    発生箇所: ExcelFile._sheet() / ExcelComHandler._sheet()
    """

    MSG = "シートが見つかりません: {name}  存在するシート: {sheets}"


class MacroError(ExcelError):
    """VBA マクロの実行に失敗した場合。

    発生箇所: ExcelFile.run_macro() / ExcelComHandler.run_macro()
    """


class ColumnNotFoundError(OriginalLibsError):
    """期待するカラムが見つからない場合（Excel・CSV 共通）。

    非エンジニアが列名を変更したときに分かりやすいメッセージを出すために使う。

    使い方:
        from comken.exceptions import ColumnNotFoundError

        REQUIRED_COLUMNS = ["日付", "担当者", "金額"]

        def validate_columns(rows: list[dict], required: list[str]) -> None:
            missing = set(required) - set(rows[0].keys())
            if missing:
                raise ColumnNotFoundError(
                    ColumnNotFoundError.MSG_EXCEL.format(columns=", ".join(missing))
                )
    """

    MSG_EXCEL = (
        "Excelのヘッダーが正しくありません。\n"
        "見つからない列: {columns}\n"
        "Excelの1行目を確認してください。"
    )
    MSG_CSV = (
        "CSVに列が見つかりません: {columns}\n"
        "存在する列: {existing}\n"
        "CSVのヘッダー（1行目）が変更されていないか確認してください。"
    )
    MSG_KEY = "キー列が見つかりません: {key}\n存在する列: {existing}"


class CsvError(OriginalLibsError):
    """CSV 操作に関する例外の基底クラス。"""

    MSG_ENCODING = (
        "文字コードを判定できませんでした（UTF-8 / CP932 のどちらでも読めません）: {path}\n"
        "CsvReader(path, encoding='文字コード名') で明示してください。"
    )
    MSG_HEADERS_TOO_FEW = (
        "headers の列数（{expected}列）が CSV の列数より少ないため、"
        "はみ出した列のデータが失われます: {path}\n"
        "headers にすべての列名を指定してください。"
    )


class ConfigError(OriginalLibsError):
    """設定ファイルに関する例外。

    発生箇所: Config.__init__() でファイルが見つからない場合。
    """

    MSG = (
        "config.ini が見つかりません: {path}\n"
        "config.ini.example をコピーして config.ini を作成してください。"
    )
    MSG_STUB_TARGET = (
        "補完スタブの出力先が見つかりません: {path}\n"
        "src/config.py（from comken.config import Config / config = Config()）を"
        "作成してから実行してください。"
    )


# ── 型変換の警告 ──────────────────────────────────────────────────────────────


class Warnings:
    """ライブラリが発行する UserWarning のメッセージテンプレート。"""

    COERCION = "{param} に {type_name}（{value!r}）が渡されました。{expected} に変換します。"


def _warn_coerce(value: Any, expected: type[_T], param: str, stacklevel: int = 3) -> _T:
    """型が違う場合に警告して変換する。ライブラリ内部用。

    型が一致していれば何もしない。違う場合だけ UserWarning を発行して変換する。
    None が渡された場合は TypeError を発生させる（"None" という文字列に変換しない）。
    stacklevel はユーザーコードの行番号を警告に表示するために調整する。
    """
    if value is None:
        raise TypeError(f"{param} に None が渡されました。{expected.__name__} を渡してください。")
    if not isinstance(value, expected):
        warnings.warn(
            Warnings.COERCION.format(
                param=param,
                type_name=type(value).__name__,
                value=value,
                expected=expected.__name__,
            ),
            UserWarning,
            stacklevel=stacklevel,
        )
    return expected(value)
