"""comken/toolbox/windows/__init__.py — Windows 固有の操作 API を公開するパッケージ。"""

from comken.toolbox.windows.excel_com import ExcelCOMHandler
from comken.toolbox.windows.paths import Paths
from comken.toolbox.windows.process import is_excel_running, kill_excel
from comken.toolbox.windows.registry import RegistryHandler
from comken.toolbox.windows.window import WindowHandler

__all__ = [
    "ExcelCOMHandler",
    "WindowHandler",
    "RegistryHandler",
    "Paths",
    "is_excel_running",
    "kill_excel",
]
