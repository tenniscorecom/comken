"""comken/windows/__init__.py — Windows 固有の操作 API を公開するパッケージ。"""

from .handler import ExcelComHandler, RegistryHandler, WindowHandler
from .process import is_excel_running, kill_excel

__all__ = [
    "ExcelComHandler",
    "WindowHandler",
    "RegistryHandler",
    "is_excel_running",
    "kill_excel",
]
