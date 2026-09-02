"""comken/internal/__init__.py — 社内ライブラリ呼び出しの共通玄関。

社内 LAN 環境にだけ存在する社内ライブラリ（例: ``example_libs.rpa``）を
プロジェクトから呼ぶときの例外変換・共通定数の窓口を提供する。
社内ライブラリ自体は ``from example_libs import ...`` の**静的 import** で
読み込み、``comken.internal.base.raise_if_target_missing`` で
``InternalLibraryNotFoundError`` に変換する。
"""

from comken.internal.exceptions import (
    InternalLibraryError,
    InternalLibraryNotFoundError,
    InternalLibraryVersionMismatchError,
)

__all__ = [
    "InternalLibraryError",
    "InternalLibraryNotFoundError",
    "InternalLibraryVersionMismatchError",
]
