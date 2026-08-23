"""comken/exceptions/rpa.py — 旧 RpaError 系の後方互換シム。

実体は ``comken.internal.exceptions.InternalLibraryError`` 系に移動済み。
旧名称は遅延 ``__getattr__`` で公開しているので、 ``import comken.exceptions``
だけでは警告は出ず、 ``comken.exceptions.RpaError`` のように
実際に属性を取り出したときだけ ``FutureWarning`` が出る。

    # 旧（動くが FutureWarning が出る）
    from comken.exceptions import RpaLibraryNotFoundError

    # 新（推奨）
    from comken.internal.exceptions import InternalLibraryNotFoundError

旧例外は新例外の **同じクラスそのもの** として解決されるよう
``__getattr__`` で同じクラスオブジェクトを返すシムを維持している。
そのため ``except RpaLibraryNotFoundError`` で
新しい ``InternalLibraryNotFoundError`` も捕捉できる（``is`` 比較で同一になる）。
"""

import warnings

from comken.internal.exceptions import (
    InternalLibraryError,
    InternalLibraryNotFoundError,
    InternalLibraryVersionMismatchError,
)

_WARN_MESSAGE = (
    "RpaError / RpaLibraryNotFoundError は comken.internal.exceptions に移動しました。"
    "新名称を使用してください。"
)


def __getattr__(name: str) -> object:
    """旧名称を取り出した瞬間に警告して新例外クラスを返す。"""
    if name == "RpaError":
        warnings.warn(_WARN_MESSAGE, FutureWarning, stacklevel=2)
        return InternalLibraryError
    if name == "RpaLibraryNotFoundError":
        warnings.warn(_WARN_MESSAGE, FutureWarning, stacklevel=2)
        return InternalLibraryNotFoundError
    if name == "RpaLibraryVersionMismatchError":
        warnings.warn(_WARN_MESSAGE, FutureWarning, stacklevel=2)
        return InternalLibraryVersionMismatchError
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# `__getattr__` で遅延解決する名前を `__all__` に列挙する（モジュール読込時に属性は未定義）
__all__ = ["RpaError", "RpaLibraryNotFoundError", "RpaLibraryVersionMismatchError"]  # noqa: F822
