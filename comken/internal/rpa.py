"""comken/internal/rpa.py — 社内 RPA 基盤呼び出しの薄いラッパー。

``comken.internal.base.InternalLibraryBase`` を使って
``example_libs.v0000.rpa`` を 1 か所でロードする。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from comken.internal.base import InternalLibraryBase, ModuleType

logger = logging.getLogger(__name__)

RPA_LIBRARY_NAME = "example_libs.v0000.rpa"


def _call(rpa: ModuleType, target: str, main: Callable[[], Any], project_name: str) -> Any:
    """社内 RPA 基盤の入口を呼ぶ。"""
    logger.info("%s で %s を開始します", target, project_name)
    return getattr(rpa, target).rpta(main, project_name)


def backoffice(main: Callable[[], Any], project_name: str) -> Any:
    """バックオフィスの RPA として main を実行する。"""
    with InternalLibraryBase(RPA_LIBRARY_NAME) as rpa:
        return _call(rpa, "backoffice", main, project_name)


def intranet(main: Callable[[], Any], project_name: str) -> Any:
    """イントラネットの RPA として main を実行する。"""
    with InternalLibraryBase(RPA_LIBRARY_NAME) as rpa:
        return _call(rpa, "intranet", main, project_name)


__all__ = ["backoffice", "intranet", "RPA_LIBRARY_NAME"]
