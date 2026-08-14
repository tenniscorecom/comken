"""comken/utils/files/base.py — 1つのファイルを扱うクラスに共通する薄い基底クラス。"""

from __future__ import annotations

from pathlib import Path

from ...exceptions.file import UnsupportedFileSuffixError


class FileBase:
    """パスの正規化と拡張子検証だけを提供する。"""

    SUFFIXES: tuple[str, ...] = ()

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        if self.SUFFIXES and self._path.suffix.lower() not in self.SUFFIXES:
            raise UnsupportedFileSuffixError(self._path, self.SUFFIXES)

    @property
    def path(self) -> Path:
        """正規化したファイルパスを返す。"""
        return self._path
