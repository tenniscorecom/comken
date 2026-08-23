"""comken/core/table/__init__.py — メモリ上の Table 同士の純粋な操作。

データモデルと Table 間の転記（Transfer）を置く。ファイル I/O を含む
アダプタは toolbox 側に置き、保存の挙動が境界で見えるようにする。
"""

from comken.core.table.comparison import TableComparison, compare_tables
from comken.core.table.model import Table
from comken.core.table.transfer import Transfer

__all__ = ["Table", "TableComparison", "Transfer", "compare_tables"]
