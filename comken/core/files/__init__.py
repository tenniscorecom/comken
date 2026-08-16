"""comken/core/files/__init__.py — ファイル関連機能の公開窓口

検索・操作・圧縮・命名をまとめて公開する。

パス取得（``Paths``）はレジストリを触るため toolbox/windows/ へ移した。
コアの外にあるものを触らない、という ``comken.core`` の定義に従ったもの。
"""

from .archive import unzip, zip_files, zip_folder
from .finder import FileFinder, date_in_name
from .naming import DateNameBuilder
from .ops import copy_file, local_copy, move_file, project_dir

__all__ = [
    "FileFinder",
    "date_in_name",
    "move_file",
    "project_dir",
    "copy_file",
    "local_copy",
    "zip_folder",
    "zip_files",
    "unzip",
    "DateNameBuilder",
]
