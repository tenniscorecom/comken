"""列が見つからない場合の例外。"""

from .base import ComkenError


class ColumnNotFoundError(ComkenError):
    """Excel・CSV・データ比較で列が見つからないエラー

    対処:
        画面に表示された具体的なエラー名を上の表から探す
    """


class ExcelColumnNotFoundError(ColumnNotFoundError):
    """Excel の列見出しが見つからない

    非エンジニアが列名を変更したときに分かりやすいメッセージを出すために使う。

    発生箇所: 利用側プロジェクトの列検証処理（現在 comken 内からは未送出）

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


class CsvColumnNotFoundError(ColumnNotFoundError):
    """CSV の列見出しが見つからない

    非エンジニアが列名を変更したときに分かりやすいメッセージを出すために使う。

    発生箇所: CsvReader._validate_columns()

    使い方:
        from comken.exceptions import CsvColumnNotFoundError

        REQUIRED_COLUMNS = ["日付", "担当者", "金額"]

        def validate_columns(rows: list[dict[str, str]], required: list[str]) -> None:
            existing = list(rows[0])
            missing = [column for column in required if column not in existing]
            if missing:
                raise CsvColumnNotFoundError(missing, existing)

    対処:
        CSV の1行目を確認する
    """

    def __init__(self, columns: list[str], existing: list[str]) -> None:
        super().__init__(
            f"CSVに列が見つかりません: {', '.join(columns)}\n"
            f"存在する列: {', '.join(existing)}\n"
            "CSVのヘッダー（1行目）が変更されていないか確認してください。"
        )


class KeyColumnNotFoundError(ColumnNotFoundError):
    """比較に使うキー列が見つからない

    発生箇所: diff_rows()

    対処:
        Excel・CSV の列名を確認する
    """

    def __init__(self, key: str, existing: list[str]) -> None:
        super().__init__(f"キー列が見つかりません: {key}\n存在する列: {', '.join(existing)}")


class InvalidColumnError(ComkenError):
    """列の指定が正しくない（打ち間違いなど）

    対処:
        列は番号（1, 2, …）か列記号（"A", "AA"）で指定する
    """

    def __init__(self, column: str) -> None:
        super().__init__(
            f"列の指定が正しくありません: {column!r}\n"
            '列番号（1始まり）または列記号で指定してください（例: 1, "A", "AA"）。'
        )
