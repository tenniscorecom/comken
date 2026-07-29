"""comken の例外体系。

OriginalLibsError
├── UnsupportedFileSuffixError
├── ExcelError
│   ├── ExcelFileNotFoundError
│   ├── SheetNotFoundError
│   ├── MacroError
│   ├── RowTransferError
│   ├── EmptyHeaderCellError
│   ├── ExcelHeadersTooFewError
│   └── FileFormatMismatchError
├── CsvError
│   ├── EncodingDetectionError
│   ├── CsvHeadersTooFewError
│   ├── CsvNoDataRowsError
│   └── CsvCellReferenceError
├── ColumnNotFoundError
│   ├── ExcelColumnNotFoundError
│   ├── CsvColumnNotFoundError
│   └── KeyColumnNotFoundError
└── ConfigError
    ├── ConfigFileNotFoundError
    └── ConfigSectionNotFoundError

カテゴリ基底クラスはまとめて捕捉するために使い、直接送出しない。
"""

from .base import OriginalLibsError
from .column import (
    ColumnNotFoundError,
    CsvColumnNotFoundError,
    ExcelColumnNotFoundError,
    KeyColumnNotFoundError,
)
from .config import (
    ConfigError,
    ConfigFileNotFoundError,
    ConfigSectionNotFoundError,
)
from .csv import (
    CsvCellReferenceError,
    CsvError,
    CsvHeadersTooFewError,
    CsvNoDataRowsError,
    EncodingDetectionError,
)
from .excel import (
    EmptyHeaderCellError,
    ExcelError,
    ExcelFileNotFoundError,
    ExcelHeadersTooFewError,
    FileFormatMismatchError,
    MacroError,
    RowTransferError,
    SheetNotFoundError,
)
from .file import UnsupportedFileSuffixError
from .warning import _warn_coerce as _warn_coerce

__all__ = [
    "OriginalLibsError",
    "ExcelError",
    "ExcelFileNotFoundError",
    "SheetNotFoundError",
    "MacroError",
    "RowTransferError",
    "EmptyHeaderCellError",
    "ExcelHeadersTooFewError",
    "FileFormatMismatchError",
    "CsvError",
    "EncodingDetectionError",
    "CsvHeadersTooFewError",
    "CsvNoDataRowsError",
    "CsvCellReferenceError",
    "ColumnNotFoundError",
    "ExcelColumnNotFoundError",
    "CsvColumnNotFoundError",
    "KeyColumnNotFoundError",
    "ConfigError",
    "ConfigFileNotFoundError",
    "ConfigSectionNotFoundError",
    "UnsupportedFileSuffixError",
]
