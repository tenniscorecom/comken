"""列が見つからない場合の例外。"""

from .base import OriginalLibsError


class ColumnNotFoundError(OriginalLibsError):
    """列不在エラーをまとめて捕捉するための基底クラス。"""


class ExcelColumnNotFoundError(ColumnNotFoundError):
    """Excel に必要な列が存在しない場合。

    非エンジニアが列名を変更したときに分かりやすいメッセージを出すために使う。

    発生箇所: 利用側プロジェクトの列検証処理（現在 comken 内からは未送出）

    使い方:
        from comken.exceptions import ExcelColumnNotFoundError

        REQUIRED_COLUMNS = ["日付", "担当者", "金額"]

        def validate_columns(rows: list[dict[str, str]], required: list[str]) -> None:
            missing = [column for column in required if column not in rows[0]]
            if missing:
                raise ExcelColumnNotFoundError(missing)
    """

    def __init__(self, columns: list[str]) -> None:
        super().__init__(
            "Excelのヘッダーが正しくありません。\n"
            f"見つからない列: {', '.join(columns)}\n"
            "Excelの1行目を確認してください。"
        )


class CsvColumnNotFoundError(ColumnNotFoundError):
    """CSV に必要な列が存在しない場合。

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
    """

    def __init__(self, columns: list[str], existing: list[str]) -> None:
        super().__init__(
            f"CSVに列が見つかりません: {', '.join(columns)}\n"
            f"存在する列: {', '.join(existing)}\n"
            "CSVのヘッダー（1行目）が変更されていないか確認してください。"
        )


class KeyColumnNotFoundError(ColumnNotFoundError):
    """差分比較のキー列が存在しない場合。

    発生箇所: diff_rows()
    """

    def __init__(self, key: str, existing: list[str]) -> None:
        super().__init__(f"キー列が見つかりません: {key}\n存在する列: {', '.join(existing)}")


class InvalidColumnError(OriginalLibsError):
    """Excel の列指定が A / AA 形式でない場合。"""

    def __init__(self, column: str) -> None:
        super().__init__(
            f"列の指定が正しくありません: {column!r}\n"
            '列番号（1始まり）または列記号で指定してください（例: 1, "A", "AA"）。'
        )
