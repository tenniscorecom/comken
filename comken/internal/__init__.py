"""comken/internal/__init__.py — 社内ライブラリ呼び出しの共通玄関。

社内 LAN 環境にだけ存在する社内ライブラリ（例: ``example_libs.v0000.*``）を
プロジェクトから呼ぶとき、バージョン違いを気にせず取り込める窓口を提供する。
"""

from comken.internal.base import (
    InternalLibraryBase,
    find_internal_library,
    is_internal_library_available,
)
from comken.internal.exceptions import (
    InternalLibraryError,
    InternalLibraryNotFoundError,
    InternalLibraryVersionMismatchError,
)

__all__ = [
    "InternalLibraryBase",
    "InternalLibraryError",
    "InternalLibraryNotFoundError",
    "InternalLibraryVersionMismatchError",
    "is_internal_library_available",
    "find_internal_library",
]
