"""comken の例外体系。

OriginalLibsError
├── UnsupportedFileSuffixError
├── AccessError
│   ├── AccessFileNotFoundError
│   ├── AccessBackupError
│   ├── AccessLocalCopyError
│   ├── AccessRoutineError
│   └── AccessSourceNotFoundError
├── OutlookError
│   ├── ClassicOutlookNotAvailableError
│   ├── OutlookFolderNotFoundError
│   └── OutlookAttachmentNotFoundError
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
├── InvalidColumnError
├── ColumnNotFoundError
│   ├── ExcelColumnNotFoundError
│   ├── CsvColumnNotFoundError
│   └── KeyColumnNotFoundError
└── ConfigError
    ├── ConfigFileNotFoundError
    └── ConfigSectionNotFoundError

カテゴリ基底クラスはまとめて捕捉するために使い、直接送出しない。
"""

from .access import (
    AccessBackupError,
    AccessError,
    AccessFileNotFoundError,
    AccessLocalCopyError,
    AccessRoutineError,
    AccessSourceNotFoundError,
)
from .base import OriginalLibsError
from .column import (
    ColumnNotFoundError,
    CsvColumnNotFoundError,
    ExcelColumnNotFoundError,
    InvalidColumnError,
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
from .outlook import (
    ClassicOutlookNotAvailableError,
    OutlookAttachmentNotFoundError,
    OutlookError,
    OutlookFolderNotFoundError,
)
from .warning import _warn_coerce as _warn_coerce

__all__ = [
    "OriginalLibsError",
    "AccessError",
    "AccessBackupError",
    "AccessFileNotFoundError",
    "AccessLocalCopyError",
    "AccessRoutineError",
    "AccessSourceNotFoundError",
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
    "InvalidColumnError",
    "ConfigError",
    "ConfigFileNotFoundError",
    "ConfigSectionNotFoundError",
    "UnsupportedFileSuffixError",
    "OutlookError",
    "ClassicOutlookNotAvailableError",
    "OutlookFolderNotFoundError",
    "OutlookAttachmentNotFoundError",
]
