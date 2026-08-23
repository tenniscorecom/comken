"""comken/exceptions/table.py — CSV・Excel 共通の表データ API に関する例外。"""

from comken.exceptions.base import ComkenError


class TableError(ComkenError):
    """表データの読み書き・転記に関するエラー

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


class TableRowColumnsError(TableError):
    """行の列名が Table.columns と一致しない

    対処:
        不足列と余分な列を直す。列を絞る場合は select() を使う
    """

    def __init__(self, row_number: int, missing: list[str], extra: list[str]) -> None:
        super().__init__(
            f"Table の{row_number}件目の列名が columns と一致しません。"
            f"不足列: {missing}、余分な列: {extra}。列を絞る場合は select() を使ってください。"
        )


class TableTypeConversionError(TableError):
    """Table の値を指定型へ変換できない

    対処:
        表示された行番号・列名の値を、指定した型へ変換できる内容に直す
    """

    def __init__(self, row_number: int, column: str, value: object) -> None:
        super().__init__(
            f"Table の{row_number}件目、列「{column}」の値「{value}」を型変換できません。"
        )


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

    発生箇所: Table.index() / Table.merge() / compare_tables()

    対処:
        キー列の値を一意にしてから処理をやり直す
    """

    def __init__(self, columns: list[str], key: object) -> None:
        super().__init__(
            f"列「{','.join(columns)}」のキー「{key}」が重複しています。キーを一意にしてください。"
        )


class TableMergeSuffixError(TableError):
    """Table.merge() の suffixes が列名を安全に作れない。

    対処:
        空でなく互いに異なる2つの文字列を suffixes に指定する
    """

    def __init__(self) -> None:
        super().__init__(
            "merge の suffixes には、空でなく互いに異なる2つの文字列を指定してください。"
        )


class TableMergeColumnCollisionError(TableError):
    """Table.merge() で生成する列名が既存の列名と衝突する。

    対処:
        suffixes を変更し、結合後のすべての列名が一意になるようにする
    """

    def __init__(self, columns: list[str]) -> None:
        super().__init__(
            f"merge 後の列名が重複します: {columns}。"
            "suffixes を変更し、すべて異なる列名にしてください。"
        )


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


class TransferTransformError(TransferRowError):
    """transform コールバック内で例外が発生した

    発生箇所: Transfer.run()

    対処:
        エラーメッセージに表示された転記元の行番号・キー・元の例外を確認する
    """

    def __init__(
        self,
        row_number: int,
        key: tuple,
        source_row: dict | None,
        original: Exception,
    ) -> None:
        self.row_number = row_number
        self.key = key
        self.source_row = source_row
        self.original = original
        super().__init__(
            row_number,
            f"transform の実行に失敗しました(行{row_number}、キー {key}): {original}",
        )


class InvalidTransferResultError(TransferRowError):
    """transform の戻り値が TransferResult でない

    発生箇所: Transfer.run()

    対処:
        transform は TransferResult.APPLY / SKIP / STOP のいずれかを返す
    """

    def __init__(self, row_number: int, value: object) -> None:
        self.value = value
        super().__init__(
            row_number,
            f"transform の戻り値は TransferResult を返してください: {value!r}",
        )
