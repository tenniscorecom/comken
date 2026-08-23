"""comken/internal/base.py — 社内ライブラリ呼び出しを束ねる基底クラス。"""

from __future__ import annotations

import importlib
import importlib.util
import logging
from types import TracebackType
from typing import TypeAlias

from comken.internal.exceptions import InternalLibraryNotFoundError

logger = logging.getLogger(__name__)

ModuleType: TypeAlias = object  # importlib.util.types.ModuleType


class InternalLibraryBase:
    """社内ライブラリのモジュールを束ねるラッパークラス。

    利用例::

        with InternalLibraryBase("example_libs.v0000.rpa") as rpa:
            rpa.backoffice(main, "project")
    """

    def __init__(self, library_name: str) -> None:
        self._library_name = library_name
        self._module: ModuleType | None = None

    @property
    def library_name(self) -> str:
        return self._library_name

    def find_spec(self) -> bool:
        """社内ライブラリが import 可能なら True。"""
        return importlib.util.find_spec(self._library_name) is not None

    def load(self) -> ModuleType:
        """社内ライブラリを import して返す。失敗時は InternalLibraryNotFoundError。"""
        try:
            return importlib.import_module(self._library_name)
        except ImportError as exc:
            raise InternalLibraryNotFoundError(self._library_name) from exc

    def __enter__(self) -> ModuleType:
        if not self.find_spec():
            logger.warning("社内ライブラリ %s は見つかりません。", self._library_name)
        self._module = self.load()
        return self._module

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._module = None


# 後方互換性のために、「見つける／ラップ」も残す
def is_internal_library_available(library_name: str) -> bool:
    """社内ライブラリが import 可能なら True。"""
    return importlib.util.find_spec(library_name) is not None


def find_internal_library(library_name: str) -> ModuleType | None:
    """社内ライブラリを import して返す。無ければ None。"""
    try:
        return importlib.import_module(library_name)
    except ImportError:
        return None
