"""comken/toolbox/windows/registry.py — レジストリ値の読み取り（pywin32）

with 文で確実にキーを閉じる。
"""

from __future__ import annotations

from types import TracebackType
from typing import Self

import win32api

from comken.core.timer import measure


class RegistryHandler:
    """レジストリ値の読み取りクラス。with 文で確実にキーを閉じる。"""

    def __init__(self, hive: int, key_path: str) -> None:
        """
        Args:
            hive: レジストリのルートキー（例: win32con.HKEY_CURRENT_USER）。
            key_path: キーのパス（例: r"Software\\MyApp"）。
        """
        self._key = win32api.RegOpenKey(hive, key_path)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    @measure
    def read(self, value_name: str) -> str:
        """レジストリ値を読み取る。

        Args:
            value_name: 読み取る値の名前。

        Returns:
            レジストリ値の文字列。
        """
        value, _ = win32api.RegQueryValueEx(self._key, value_name)
        return value

    @measure
    def close(self) -> None:
        """レジストリキーを閉じる。with 文を使う場合は自動で呼ばれる。"""
        win32api.RegCloseKey(self._key)
