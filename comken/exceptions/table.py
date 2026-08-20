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
        通常は何も返さず、1件を除外する場合は Transfer.SKIP、全体を止める場合は Transfer.STOP を返す
    """

    def __init__(self, row_number: int, reason: str) -> None:
        super().__init__(f"転記元の{row_number}件目を処理できません。{reason}")


class TransferDestinationRowMissingError(ComkenError):
    """転記先に対応する行がない状態で transform がその行を操作した

    発生箇所: Transfer.run()

    対処:
        destination_row が None か確認し、新規行を処理するか Transfer.SKIP を返す
    """

    def __init__(self, row_number: int) -> None:
        super().__init__(
            f"転記元の{row_number}件目に対応する転記先行がありません。"
            "destination_row が None か確認し、新規行を処理するか "
            "Transfer.SKIP を返してください。"
        )


class TransferDestinationMultipleMatchError(ComkenError):
    """転記先のキーに一致する行が複数ある

    発生箇所: Transfer.run()

    対処:
        mapping の先頭列に対応する転記先列の値を一意にする
    """

    def __init__(self, key_column: str, key: object) -> None:
        super().__init__(
            f"転記先列「{key_column}」のキー「{key}」に一致する行が複数あります。"
            "転記先のキーを一意にしてください。"
        )
