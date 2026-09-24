"""comken/exceptions/column.py — 列が見つからない場合の例外。"""

from comken.exceptions.base import ComkenError


class ColumnNotFoundError(ComkenError):
    """Excel・CSV・データ比較で列が見つからないエラー

    対処:
        画面に表示された具体的なエラー名を上の表から探す
    """


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
