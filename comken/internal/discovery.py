"""comken/internal/discovery.py — 社内ライブラリのバージョン検出ユーティリティ。"""

from __future__ import annotations

import importlib
import re
from typing import Any

_VERSION_RE = re.compile(r"\.v(\d+(?:\.\d+)*)")


def parse_internal_library_version(library_name: str) -> str | None:
    """ライブラリ名からバージョン部分を取り出す。

    例:
        ``example_libs.v0000.rpa`` -> ``"0000"``
        ``example_libs.v1.2.rpa`` -> ``"1.2"``
    """
    match = _VERSION_RE.search(library_name)
    return match.group(1) if match else None


def get_internal_library_version(library_name: str) -> str | None:
    """実際に import したモジュールのバージョン属性を取得する。"""
    try:
        module = importlib.import_module(library_name)
    except ImportError:
        return None
    version: Any = getattr(module, "__version__", None)
    return str(version) if version is not None else None
