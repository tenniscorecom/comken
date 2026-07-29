"""CSV 操作に関する例外。"""

from pathlib import Path

from .base import OriginalLibsError


class CsvError(OriginalLibsError):
    """CSV 操作に関する例外をまとめて捕捉するための基底クラス。"""


class EncodingDetectionError(CsvError):
    """CSV の文字コードを自動判定できない場合。

    発生箇所: CsvReader._read_text()
    """

    def __init__(self, path: Path | str) -> None:
        super().__init__(
            "文字コードを判定できませんでした（UTF-8 / CP932 のどちらでも読めません）: "
            f"{path}\nCsvReader(path, encoding='文字コード名') で明示してください。"
        )


class CsvHeadersTooFewError(CsvError):
    """指定したヘッダー数が CSV の列数より少ない場合。

    発生箇所: CsvReader._load()
    """

    def __init__(self, expected: int, path: Path | str) -> None:
        super().__init__(
            f"headers の列数（{expected}列）が CSV の列数より少ないため、"
            f"はみ出した列のデータが失われます: {path}\n"
            "headers にすべての列名を指定してください。"
        )


class CsvNoDataRowsError(CsvError):
    """CSV にデータ行が1行もない場合。

    発生箇所: CsvReader.first()
    """

    def __init__(self, path: Path | str) -> None:
        super().__init__(
            f"CSV にデータ行がありません: {path}\n"
            "ヘッダー行の下に、読み取るデータが1行以上あることを確認してください。"
        )


class CsvRowNotFoundError(CsvError):
    """キーに一致する行が CSV に無い場合。

    発生箇所: CsvReader.find()
    """

    def __init__(self, key_col: str, value: str, path: Path | str) -> None:
        super().__init__(
            f"「{key_col}」が「{value}」の行が見つかりません: {path}\n"
            "値の書き方（前後の空白・全角半角・ゼロ埋め）が元データと合っているか確認してください。\n"
            "この行が無くても処理を続けてよい場合は find(..., required=False) を指定します。"
        )


class CsvCellReferenceError(CsvError):
    """CSV のセル参照が不正、または範囲外の場合。

    発生箇所: CsvReader.cell()
    """

    def __init__(self, ref: str, path: Path | str, detail: str) -> None:
        super().__init__(
            f"CSV のセル「{ref}」を読み取れませんでした: {path}\n"
            f"{detail}。A1 や B2 のように、CSV を開いたときに存在するセルを指定してください。"
        )
