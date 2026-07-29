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
