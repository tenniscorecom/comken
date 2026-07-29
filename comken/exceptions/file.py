"""ファイル形式の検証に関する例外。"""

from pathlib import Path

from .base import ComkenError


class UnsupportedFileSuffixError(ComkenError):
    """扱えない拡張子のファイルが指定された。"""

    def __init__(self, path: Path, suffixes: tuple[str, ...]) -> None:
        expected = "、".join(suffixes)
        super().__init__(
            f"対応していないファイル形式です: {path}\n"
            f"拡張子が {expected} のファイルを指定してください。"
        )
