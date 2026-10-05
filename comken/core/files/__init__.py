"""comken/core/files/__init__.py — ファイル関連機能の公開窓口

検索・操作・圧縮をまとめて公開する。
"""

from comken.core.files.archive import unzip, zip_files, zip_folder
from comken.core.files.atomic import atomic_write
from comken.core.files.finder import find_dated_file
from comken.core.files.ops import (
    copy_file,
    delete_file,
    delete_files,
    local_copy,
    move_file,
    project_dir,
)

__all__ = [
    "atomic_write",
    "copy_file",
    "delete_file",
    "delete_files",
    "find_dated_file",
    "local_copy",
    "move_file",
    "project_dir",
    "unzip",
    "zip_files",
    "zip_folder",
]
