"""ファイルの検索・操作・圧縮・パス取得・命名をまとめたパッケージ。"""

from .archive import unzip, zip_files, zip_folder
from .finder import FileFinder
from .naming import DateNameBuilder
from .ops import copy_file, local_copy, move_file
from .paths import Paths

__all__ = [
    "FileFinder",
    "Paths",
    "move_file",
    "copy_file",
    "local_copy",
    "zip_folder",
    "zip_files",
    "unzip",
    "DateNameBuilder",
]
