"""comken/core/files/base.py — 1つのファイルを扱うクラスに共通する薄い基底クラス。

Excel の内部基底クラスなど、
「1つのファイルを読み書きするクラス」の共通祖先。サブクラス側で ``SUFFIXES``
を宣言しておくと、``__init__`` で拡張子を自動で検証して
``UnsupportedFileSuffixError`` を投げる。
"""

from pathlib import Path

from comken.exceptions.file import UnsupportedFileSuffixError


class FileBase:
    """パス正規化と拡張子検証だけを提供する基底クラス。

    サブクラスで ``SUFFIXES`` に許可する拡張子のタプルを宣言する
    （空タプルのままなら検証しない）。``__init__`` で ``path`` を ``Path`` に直し、
    拡張子が ``SUFFIXES`` に無ければ ``UnsupportedFileSuffixError`` を投げる。

    利用側は ``self._path`` ではなく ``self.path`` プロパティで読む。
    （``_path`` は将来 Path 以外の形に差し替える余地として、サブクラスから触らないため）
    """

    SUFFIXES: tuple[str, ...] = ()

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        if self.SUFFIXES and self._path.suffix.lower() not in self.SUFFIXES:
            raise UnsupportedFileSuffixError(self._path, self.SUFFIXES)

    @property
    def path(self) -> Path:
        """正規化したファイルパスを返す。"""
        return self._path
