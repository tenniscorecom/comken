"""comken/exceptions/file.py — ファイル形式の検証に関する例外。"""

from pathlib import Path

from comken.exceptions.base import ComkenError


class UnsupportedFileSuffixError(ComkenError):
    """対応外の拡張子が指定された

    対処:
        CSV / Excel の対応する拡張子のファイルを指定する
    """

    def __init__(self, path: Path, suffixes: tuple[str, ...]) -> None:
        expected = "、".join(suffixes)
        super().__init__(
            f"対応していないファイル形式です: {path}\n"
            f"拡張子が {expected} のファイルを指定してください。"
        )
