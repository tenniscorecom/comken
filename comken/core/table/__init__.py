"""comken/core/table/__init__.py — メモリ上の Table 同士の純粋な操作。

データモデルと Table 間の転記（``transfer``）を置く。ファイル I/O を含む
アダプタは toolbox 側に置き、保存の挙動が境界で見えるようにする。
"""

from comken.core.table.diff import DiffResult
from comken.core.table.hierarchy import HierarchyResult
from comken.core.table.model import Table
from comken.core.table.transfer import TransferResult, transfer

__all__ = [
    "DiffResult",
    "HierarchyResult",
    "Table",
    "TransferResult",
    "transfer",
]
