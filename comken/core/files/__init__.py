"""comken/core/files/__init__.py — ファイル関連機能の公開窓口

検索・操作・圧縮・命名をまとめて公開する。

パス取得（``Paths``）はレジストリを触るため toolbox/windows/ へ移した。
コアの外にあるものを触らない、という ``comken.core`` の定義に従ったもの。
"""

from comken.core.files.archive import unzip, zip_files, zip_folder
from comken.core.files.atomic import atomic_write
from comken.core.files.finder import DateFileFinder, date_in_name, dates_in_name
from comken.core.files.name import DateNameBuilder
from comken.core.files.ops import (
    copy_file,
    copy_to_local_if_large,
    delete_file,
    delete_files,
    local_copy,
    move_file,
    project_dir,
)

__all__ = [
    "DateNameBuilder",
    "DateFileFinder",
    "atomic_write",
    "copy_file",
    "copy_to_local_if_large",
    "date_in_name",
    "dates_in_name",
    "delete_file",
    "delete_files",
    "local_copy",
    "move_file",
    "project_dir",
    "unzip",
    "zip_files",
    "zip_folder",
]
