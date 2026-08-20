"""comken/exceptions/table.py — CSV・Excel 共通の表データ API に関する例外。"""

from comken.exceptions.base import ComkenError


class TableError(ComkenError):
    """表データの読み書き・転記に関するエラー。"""


class TableNotOpenError(TableError):
    """表を with 文で開かずに操作した。"""

    def __init__(self, table_type: str) -> None:
        super().__init__(f"{table_type} は with 文の中で使ってください。")


class TransferMappingError(TableError):
    """転記する列の対応が指定されていない。"""

    def __init__(self) -> None:
        super().__init__("mapping には転記元列と転記先列を指定してください。")
