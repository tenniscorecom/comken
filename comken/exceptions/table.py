"""comken/exceptions/table.py — CSV・Excel 共通の表データ API に関する例外。"""

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


class InvalidTableOperationError(TableError):
    """Table API で実行できない操作が指定された。

    発生箇所: Table / CSV / ExcelTable

    対処:
        対象が読み取り専用でないか、指定したテーブル名が正しいか確認する
    """


class TableNotOpenError(TableError):
    """表を with 文で開かずに操作した。

    対処:
        ``with`` 文の中で使う（CSV / Excel などは ``__enter__`` で表を開く）
    """

    def __init__(self, table_type: str) -> None:
        super().__init__(f"{table_type} は with 文の中で使ってください。")


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

    発生箇所: Table.index() / compare_tables()

    対処:
        キー列の値を一意にしてから処理をやり直す
    """

    def __init__(self, columns: list[str], key: object) -> None:
        super().__init__(
            f"列「{','.join(columns)}」のキー「{key}」が重複しています。キーを一意にしてください。"
        )
