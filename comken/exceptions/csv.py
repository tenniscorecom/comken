"""comken/exceptions/csv.py — CSV 操作に関する例外。"""

from __future__ import annotations

from pathlib import Path

from .base import ComkenError


class CsvError(ComkenError):
    """CSV に関するエラー

    対処:
        画面に表示された具体的なエラー名を上の表から探す
    """


class EncodingDetectionError(CsvError):
    """CSV の文字コードを判定できない

    発生箇所: CsvReader._read_text()

    対処:
        CSV の保存形式を確認し、管理者へ連絡する
    """

    def __init__(self, path: Path | str) -> None:
        super().__init__(
            "文字コードを判定できませんでした（UTF-8 / CP932 のどちらでも読めません）: "
            f"{path}\nCsvReader(path, encoding='文字コード名') で明示してください。"
        )


class CsvHeadersTooFewError(CsvError):
    """指定した見出し数が CSV の列数より少ない

    発生箇所: CsvReader._load()

    対処:
        管理者へ連絡する
    """

    def __init__(self, expected: int, path: Path | str) -> None:
        super().__init__(
            f"headers の列数（{expected}列）が CSV の列数より少ないため、"
            f"はみ出した列のデータが失われます: {path}\n"
            "headers にすべての列名を指定してください。"
        )


class CsvNoDataRowsError(CsvError):
    """CSV に見出し以外のデータ行がない

    発生箇所: CsvReader.first()

    対処:
        見出し行の下にデータが1行以上あるか確認する
    """

    def __init__(self, path: Path | str) -> None:
        super().__init__(
            f"CSV にデータ行がありません: {path}\n"
            "ヘッダー行の下に、読み取るデータが1行以上あることを確認してください。"
        )


class CsvRowNotFoundError(CsvError):
    """キーに一致する行が CSV に無い

    発生箇所: CsvReader.find()

    対処:
        探している値の書き方（前後の空白・全角半角・ゼロ埋め）を元データと見比べる
    """

    def __init__(self, key_col: str, value: str, path: Path | str) -> None:
        super().__init__(
            f"「{key_col}」が「{value}」の行が見つかりません: {path}\n"
            "値の書き方（前後の空白・全角半角・ゼロ埋め）が元データと合っているか確認してください。\n"
            "この行が無くても処理を続けてよい場合は find(..., required=False) を指定します。"
        )


class CsvRowDuplicateKeyError(CsvError):
    """キーにする列に同じ値が複数ある

    発生箇所: CsvReader.index()

    対処:
        表示された値の行を元データで確認し、重複を取り除く。重複が正しいデータなら管理者へ連絡する
    """

    def __init__(self, key_col: str, duplicates: dict[str, int], path: Path | str) -> None:
        # 件数が多いと読めないので先頭だけ出す。全部出しても直す手がかりは増えない。
        shown = list(duplicates.items())[:5]
        detail = "、".join(f"{key}（{count}件）" for key, count in shown)
        if len(duplicates) > len(shown):
            detail += f" ほか{len(duplicates) - len(shown)}件"
        super().__init__(
            f"「{key_col}」が重複しています: {detail}\n{path}\n"
            "キーが1件に決まらないと、突合の結果が変わってしまいます。"
            "元データの重複を取り除くか、重複を前提にする場合は group_by() を使ってください。"
        )


class CsvCellReferenceError(CsvError):
    """CSV のセル位置（例: A2）の指定が正しくない、または範囲外

    発生箇所: CsvReader.cell()

    対処:
        表示されたセル位置と、CSV の行数・列数を確認する
    """

    def __init__(self, ref: str, path: Path | str, detail: str) -> None:
        super().__init__(
            f"CSV のセル「{ref}」を読み取れませんでした: {path}\n"
            f"{detail}。A1 や B2 のように、CSV を開いたときに存在するセルを指定してください。"
        )
