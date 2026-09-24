"""comken/exceptions/csv.py — CSV 操作に関する例外。"""

from pathlib import Path

from comken.exceptions.base import ComkenError


class CSVError(ComkenError):
    """CSV に関するエラー

    対処:
        画面に表示された具体的なエラー名を上の表から探す
    """


class EncodingDetectionError(CSVError):
    """CSV の文字コードを判定できない

    発生箇所: 文字コード自動判定時（``comken.toolbox.csv.read_text()`` /
    ``comken.toolbox.csv.CSV.read()``）

    対処:
        CSV の保存形式を確認し、管理者へ連絡する
    """

    def __init__(self, path: Path | str) -> None:
        super().__init__(
            "文字コードを判定できませんでした（UTF-8 / CP932 のどちらでも読めません）: "
            f"{path}\nencoding 引数で明示してください。"
        )


class CSVHeaderError(CSVError):
    """CSV の見出し行に関するエラー

    見出し行がない、見出しに空欄・重複がある、新規 CSV に列を
    指定できない、といった失敗をまとめて扱う。

    対処:
        - 見出し行を追加するか、ヘッダーなし CSV なら ``columns`` を指定する
        - 1行目にある空欄・重複した見出しを直す
        - 新規 CSV に書き出すときは ``CSV(columns=[...])`` で列を指定する
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)


class CSVRowLengthError(CSVError):
    """CSV のデータ行の列数が見出し数と一致しない

    対処:
        表示された行の区切り文字と値の数を確認する
    """

    def __init__(self, path: Path | str, line_number: int, expected: int, actual: int) -> None:
        super().__init__(
            f"CSV の{line_number}行目は列数が一致しません: {path}\n"
            f"見出しは{expected}列、データは{actual}列です。"
        )
