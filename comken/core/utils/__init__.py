"""comken/core/utils/__init__.py — 汎用的なデータ・時間・文字列操作 API を公開するパッケージ。"""

from .data import DiffResult, RowChange, diff_row, diff_rows
from .retry import retry
from .text import normalize, remove_spaces, strip_spaces
from .timer import Timer, measure
from .wait import wait

__all__ = [
    "diff_row",
    "diff_rows",
    "DiffResult",
    "RowChange",
    "wait",
    "normalize",
    "strip_spaces",
    "remove_spaces",
    "retry",
    "Timer",
    "measure",
    "now",
    "today",
]
from .clock import now, today
