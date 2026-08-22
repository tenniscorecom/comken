"""comken/core/table/__init__.py — Pure in-memory table operations.

The package contains the data model and Table-to-Table transfer. File-specific
adapters stay in toolbox so saving behavior is visible at the boundary.
"""

from comken.core.table.comparison import TableComparison, compare_tables
from comken.core.table.model import Table
from comken.core.table.transfer import Transfer

__all__ = ["Table", "TableComparison", "Transfer", "compare_tables"]
