"""comken/exceptions/table.py — CSV・Excel 共通の表データ API に関する例外。"""

from comken.exceptions.base import ComkenError


class TableError(ComkenError):
    """表データの読み書き・転記に関するエラー

    発生箇所: Transfer

    対処:
        画面に表示された具体的なエラー内容を確認する
    """


class TableNotOpenError(TableError):
    """表を with 文で開かずに操作した。"""

    def __init__(self, table_type: str) -> None:
        super().__init__(f"{table_type} は with 文の中で使ってください。")


class TransferMappingError(TableError):
    """転記する列の対応が指定されていない

    発生箇所: Transfer()

    対処:
        mapping に転記元列名と転記先列名を指定する
    """

    def __init__(self) -> None:
        super().__init__("mapping には転記元列と転記先列を指定してください。")


class TransferRowError(TableError):
    """transform が処理規約に合わない値を返した

    発生箇所: Transfer.run()

    対処:
        transform から辞書、None、Transfer.STOP のいずれかを返す
    """

    def __init__(self, row_number: int, reason: str) -> None:
        super().__init__(f"転記元の{row_number}件目を処理できません。{reason}")
