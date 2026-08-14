"""comken/utils/files/paths.py — よく使う標準フォルダのパス取得。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# レジストリ「User Shell Folders」の Downloads の値名（固定 GUID）
_DOWNLOADS_GUID = "{374DE290-123F-4565-9164-39C4925E467B}"


class Paths:
    """よく使うフォルダのパスを返すユーティリティ。インスタンス化せず静的メソッドで使う。

    Desktop / Downloads は OneDrive の「既知のフォルダーの移動」で
    C:\\Users\\xxx 直下にないことがあるため、レジストリから実際の場所を取得する。

    """

    @staticmethod
    def downloads() -> Path:
        """ダウンロードフォルダのパスを返す。"""
        return _shell_folder(_DOWNLOADS_GUID, Path.home() / "Downloads")

    @staticmethod
    def desktop() -> Path:
        """デスクトップのパスを返す（OneDrive リダイレクトにも追従する）。"""
        return _shell_folder("Desktop", Path.home() / "Desktop")

    @staticmethod
    def temp_dir() -> Path:
        """システムの一時フォルダのパスを返す。"""
        return Path(tempfile.gettempdir())


def _shell_folder(value_name: str, default: Path) -> Path:
    """Windows の特殊フォルダの実際の場所をレジストリから取得する。

    OneDrive の「既知のフォルダーの移動」やユーザーによる場所変更で
    Desktop / Downloads が C:\\Users\\xxx 直下にないことがあるため、
    Path.home() 決め打ちではなくレジストリを見る。取得できなければ default を返す。
    """
    try:
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            raw, _ = winreg.QueryValueEx(key, value_name)
        return Path(os.path.expandvars(raw))
    except (OSError, ImportError):
        return default
