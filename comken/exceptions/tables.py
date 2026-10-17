"""comken/exceptions/tables.py — 表データ・列・型変換に関する例外。

_coerce_to_str ヘルパーとテーブル／列の例外をまとめる。"""

import warnings

from comken.exceptions.base import ComkenError


class TableError(ComkenError):
    """表データの読み書き・転記に関するエラー。具体的な状況はメッセージに出る

    発生箇所: Transfer

    対処:
        画面に表示された具体的なエラー内容を確認する
    """


class InvalidTableInputError(TableError):
    """Table API に対応しない入力が渡された。

    発生箇所: Table / CSV / ExcelTable

    対処:
        columns、rows、types の型と列名を確認する
    """


class TableColumnNotFoundError(TableError):
    """Table に指定された列が存在しない。

    発生箇所: Table

    対処:
        Table.columns を確認し、存在する列名を指定する
    """

    def __init__(self, columns: list[str]) -> None:
        super().__init__(f"存在しない列です: {columns}")


class TableDuplicateKeyError(TableError):
    """Table の索引または比較に使うキーが重複している。

    発生箇所: Table.index() / Table.diff()

    対処:
        キー列の値を一意にしてから処理をやり直す
    """

    def __init__(self, columns: list[str], key: object) -> None:
        super().__init__(
            f"列「{','.join(columns)}」のキー「{key}」が重複しています。キーを一意にしてください。"
        )


class ColumnNotFoundError(ComkenError):
    """Excel・CSV・データ比較で列が見つからないエラー。具体的な状況はメッセージに出る

    対処:
        メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ
    """


class ExcelColumnNotFoundError(ColumnNotFoundError):
    """Excel の列見出しが見つからない

    非エンジニアが列名を変更したときに分かりやすいメッセージを出すために使う。

    発生箇所: 利用側プロジェクトの列検証処理（comken 本体のソースからは
              送出されない。利用者プロジェクトから送出する想定）

    使い方:
        from comken.exceptions import ExcelColumnNotFoundError

        REQUIRED_COLUMNS = ["日付", "担当者", "金額"]

        def validate_columns(rows: list[dict[str, str]], required: list[str]) -> None:
            missing = [column for column in required if column not in rows[0]]
            if missing:
                raise ExcelColumnNotFoundError(missing)

    対処:
        Excel の1行目を確認する
    """

    def __init__(self, columns: list[str]) -> None:
        super().__init__(
            "Excelのヘッダーが正しくありません。\n"
            f"見つからない列: {', '.join(columns)}\n"
            "Excelの1行目を確認してください。"
        )


class TransferSourceColumnNotFoundError(ColumnNotFoundError):
    """列名転記で、lookup の転記元列が見つからない

    comken 本体のソースからは送出されない。利用者プロジェクトから送出する想定。
    例外を定義して import するだけで使え、comken 内の利用は前提としない。
    ``ExcelColumnNotFoundError`` と同じ位置づけ。

    発生箇所: 利用側プロジェクトの転記元列検証処理

    対処:
        転記元データと config.ini のマッピング左側を確認する
    """

    def __init__(self, columns: list[str], existing: list[str]) -> None:
        super().__init__(
            f"転記元の列がlookupに見つかりません: {', '.join(columns)}\n"
            f"転記元に存在する列: {', '.join(existing)}\n"
            "CSVなどの転記元データと config.ini のマッピング左側を確認してください。"
        )


class InvalidColumnError(ComkenError):
    """列の指定が正しくない（打ち間違いなど）

    対処:
        列は番号（1, 2, …）か列記号（"A", "AA"）で指定する
    """

    def __init__(self, column: str | int) -> None:
        super().__init__(
            f"列の指定が正しくありません: {column!r}\n"
            '列番号（1始まり）または列記号で指定してください（例: 1, "A", "AA"）。'
        )


class _Warnings:
    """ライブラリが発行する UserWarning のメッセージ。"""

    COERCION = "{param} に {type_name}（{value!r}）が渡されました。{expected} に変換します。"


def _coerce_to_str(value: object, param: str, stacklevel: int = 3) -> str:
    """``object`` を ``str`` に揃える。 ``None`` は ``TypeError``、 ``str`` 以外は警告して変換する。

    Args:
        value: 渡された値。 ``None`` のときは ``TypeError``。
        param: エラーメッセージ・呼び出しに添える引数名（例: ``"sheet_name"``）。
        stacklevel: ``warnings.warn`` に渡す stacklevel。呼び出し元の
                    フレームで警告させるため ``3`` を既定にする。
    """
    if value is None:
        raise TypeError(f"{param} に None が渡されました。str を渡してください。")
    if not isinstance(value, str):
        warnings.warn(
            _Warnings.COERCION.format(
                param=param,
                type_name=type(value).__name__,
                value=value,
                expected="str",
            ),
            UserWarning,
            stacklevel=stacklevel,
        )
        return str(value)
    return value
