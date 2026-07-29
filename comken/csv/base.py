"""CSV Reader / Writer に共通する設定。"""

from pathlib import Path

from ..files.base import FileBase


class CsvBase(FileBase):
    """CSV のパスと文字コードを保持する基底クラス。"""

    SUFFIXES = (".csv",)

    def __init__(self, path: str | Path, encoding: str) -> None:
        super().__init__(path)
        self._encoding = encoding
