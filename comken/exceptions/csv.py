"""comken/exceptions/csv.py — CSV 操作に関する例外。"""

from pathlib import Path

from comken.exceptions.base import ComkenError


class CsvError(ComkenError):
    """CSV に関するエラー

    対処:
        画面に表示された具体的なエラー名を上の表から探す
    """


class EncodingDetectionError(CsvError):
    """CSV の文字コードを判定できない

    発生箇所: CSV.read()

    対処:
        CSV の保存形式を確認し、管理者へ連絡する
    """

    def __init__(self, path: Path | str) -> None:
        super().__init__(
            "文字コードを判定できませんでした（UTF-8 / CP932 のどちらでも読めません）: "
            f"{path}\nCSV(path, encoding='文字コード名') で明示してください。"
        )


class CsvFileNotFoundError(CsvError):
    """読み込む CSV ファイルが存在しない

    対処:
        パスを確認する。新規出力は columns を指定して write / replace する
    """

    def __init__(self, path: Path | str) -> None:
        super().__init__(f"CSV ファイルが見つかりません: {path}")


class CsvHeaderMissingError(CsvError):
    """CSV に見出し行がない

    対処:
        見出し行を追加するか、ヘッダーなし CSV なら columns を指定する
    """

    def __init__(self, path: Path | str) -> None:
        super().__init__(
            f"CSV に見出し行がありません: {path}\n"
            "columns を指定するか、見出し行を追加してください。"
        )


class CsvInvalidHeaderError(CsvError):
    """CSV の見出しに空欄または重複がある

    対処:
        CSV の1行目にある空欄または重複した見出しを直す
    """

    def __init__(self, path: Path | str, reason: str) -> None:
        super().__init__(f"CSV の見出しが不正です: {path}\n{reason}")


class CsvRowLengthError(CsvError):
    """CSV のデータ行の列数が見出し数と一致しない

    対処:
        表示された行の区切り文字と値の数を確認する
    """

    def __init__(self, path: Path | str, line_number: int, expected: int, actual: int) -> None:
        super().__init__(
            f"CSV の{line_number}行目は列数が一致しません: {path}\n"
            f"見出しは{expected}列、データは{actual}列です。"
        )


class CsvColumnsRequiredError(CsvError):
    """空の新規 CSV に出力する列を決定できない

    対処:
        CSV(columns=[...]) または Table(columns, []) で列を指定する
    """

    def __init__(self, path: Path | str) -> None:
        super().__init__(
            f"空の新規 CSV の列を決定できません: {path}\nCSV(columns=[...]) を指定してください。"
        )
