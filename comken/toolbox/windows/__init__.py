"""comken/toolbox/windows/__init__.py — Windows 固有の操作 API を公開するパッケージ。

``RegistryHandler`` は comken 内部用。利用側で直接 import する必要はない
（``comken.toolbox.windows.paths.Paths`` 経由で使う）。
"""

from comken.toolbox.windows.excel_com import ExcelCOMHandler, FileFormat
from comken.toolbox.windows.paths import Paths
from comken.toolbox.windows.process import is_excel_running, kill_excel
from comken.toolbox.windows.window import WindowHandler

__all__ = [
    "ExcelCOMHandler",
    "FileFormat",
    "WindowHandler",
    "Paths",
    "is_excel_running",
    "kill_excel",
]
