"""comken/toolbox/windows/window.py — ウィンドウの検索・操作（pywin32）

タイトルでウィンドウを検索し、前面に表示する。
"""

from __future__ import annotations

import win32con
import win32gui

from comken.core.timer import measure
from comken.exceptions import WindowNotFoundError


class WindowHandler:
    """ウィンドウの検索・操作クラス。

    タイトルでウィンドウを検索し、前面に表示する。

    """

    def __init__(self, title: str) -> None:
        """
        Args:
            title: 検索するウィンドウのタイトル（完全一致）。

        Raises:
            WindowNotFoundError: ウィンドウが見つからない場合。
        """
        self._hwnd = win32gui.FindWindow(None, title)
        if self._hwnd == 0:
            raise WindowNotFoundError(title)

    @measure
    def activate(self) -> None:
        """ウィンドウを前面に表示する。最小化されている場合は復元する。"""
        win32gui.ShowWindow(self._hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(self._hwnd)

    @measure
    def read_title(self) -> str:
        """ウィンドウのタイトルを返す。"""
        return win32gui.GetWindowText(self._hwnd)
