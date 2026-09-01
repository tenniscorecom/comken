"""comken/internal/rpa.py — 社内 RPA 基盤呼び出しの薄いラッパー。

``comken.internal.base.InternalLibraryBase`` を使って
``example_libs.v0000.rpa`` を 1 か所でロードする。呼び出し自体は
``comken.core.runner.run`` に任せる。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from comken.core.runner import run
from comken.core.timer import measure
from comken.internal.base import InternalLibraryBase
from comken.internal.names import INTERNAL_LIBRARY_ROOT

RPA_LIBRARY_NAME = f"{INTERNAL_LIBRARY_ROOT}.rpa"


@measure
def backoffice(main: Callable[[], Any], project_name: str) -> Any:
    """バックオフィスの RPA として main を実行する。"""
    with InternalLibraryBase(RPA_LIBRARY_NAME) as rpa:
        return run(f"backoffice で {project_name}", lambda: rpa.backoffice.rpta(main, project_name))


@measure
def intranet(main: Callable[[], Any], project_name: str) -> Any:
    """イントラネットの RPA として main を実行する。"""
    with InternalLibraryBase(RPA_LIBRARY_NAME) as rpa:
        return run(f"intranet で {project_name}", lambda: rpa.intranet.rpta(main, project_name))


__all__ = ["backoffice", "intranet", "RPA_LIBRARY_NAME"]
