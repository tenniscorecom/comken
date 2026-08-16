"""comken/toolbox/windows/__init__.py — Windows 固有の操作 API を公開するパッケージ。"""

from .handler import ExcelComHandler, RegistryHandler, WindowHandler
from .paths import Paths
from .process import is_excel_running, kill_excel

__all__ = [
    "ExcelComHandler",
    "WindowHandler",
    "RegistryHandler",
    "Paths",
    "is_excel_running",
    "kill_excel",
]
