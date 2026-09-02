"""comken/internal/rpa.py — 社内 RPA 基盤呼び出しの薄いラッパー。

``example_libs.rpa`` を静的 import で読み込み、
``comken.internal.base.raise_if_target_missing`` で
``ModuleNotFoundError`` を ``InternalLibraryNotFoundError`` に変換する。
呼び出し自体は ``comken.core.runner.run`` に任せる。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from comken.core.runner import run
from comken.core.timer import measure
from comken.internal.base import raise_if_target_missing

RPA_LIBRARY_NAME = "example_libs.rpa"


@measure
def backoffice(main: Callable[[], Any], project_name: str) -> Any:
    """バックオフィスの RPA として main を実行する。"""
    try:
        # 社内 LAN にだけ存在する（自宅PC・CI では未インストール）
        from example_libs import rpa  # type: ignore[reportMissingImports]
    except ModuleNotFoundError as exc:
        raise_if_target_missing(RPA_LIBRARY_NAME, exc)
        raise
    return run(f"backoffice で {project_name}", lambda: rpa.backoffice.rpta(main, project_name))


@measure
def intranet(main: Callable[[], Any], project_name: str) -> Any:
    """イントラネットの RPA として main を実行する。"""
    try:
        # 社内 LAN にだけ存在する（自宅PC・CI では未インストール）
        from example_libs import rpa  # type: ignore[reportMissingImports]
    except ModuleNotFoundError as exc:
        raise_if_target_missing(RPA_LIBRARY_NAME, exc)
        raise
    return run(f"intranet で {project_name}", lambda: rpa.intranet.rpta(main, project_name))


__all__ = ["backoffice", "intranet", "RPA_LIBRARY_NAME"]
