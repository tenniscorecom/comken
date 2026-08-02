"""comken の例外体系。

ComkenError
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
│   ├── SheetAlreadyExistsError
│   ├── LastSheetDeletionError
│   ├── InvalidTableNameError
│   ├── TableAlreadyExistsError
│   ├── TableNotFoundError
│   ├── MacroError
│   ├── RowTransferError
│   ├── EmptyHeaderCellError
│   ├── ExcelHeadersTooFewError
│   └── FileFormatMismatchError
├── CsvError
│   ├── EncodingDetectionError
│   ├── CsvHeadersTooFewError
│   ├── CsvNoDataRowsError
│   ├── CsvRowNotFoundError
│   ├── CsvRowDuplicateKeyError
│   └── CsvCellReferenceError
├── RpaError
│   └── RpaLibraryNotFoundError
├── BrowserError
│   ├── DriverStartError
│   ├── BrowsersNotStartedError
│   ├── BrowsersClosedError
│   ├── SessionNotStartedError
│   ├── SessionClosedError
│   ├── ConcurrentSessionUseError
│   ├── SessionNameConflictError
│   ├── SessionNotFoundError
│   ├── ElementNotFoundError
│   ├── PopupTabNotOpenedError
│   └── DownloadTimeoutError
├── InvalidColumnError
├── ColumnNotFoundError
│   ├── ExcelColumnNotFoundError
│   ├── CsvColumnNotFoundError
│   └── KeyColumnNotFoundError
└── ConfigError
    ├── ConfigFileNotFoundError
    ├── ConfigCreatedFromExampleError
    ├── ConfigLowerCaseNameError
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
from .base import ComkenError
from .browser import (
    BrowserError,
    BrowsersClosedError,
    BrowsersNotStartedError,
    ConcurrentSessionUseError,
    DownloadTimeoutError,
    DriverStartError,
    ElementNotFoundError,
    PopupTabNotOpenedError,
    SessionClosedError,
    SessionNameConflictError,
    SessionNotFoundError,
    SessionNotStartedError,
)
from .column import (
    ColumnNotFoundError,
    CsvColumnNotFoundError,
    ExcelColumnNotFoundError,
    InvalidColumnError,
    KeyColumnNotFoundError,
)
from .config import (
    ConfigCreatedFromExampleError,
    ConfigError,
    ConfigFileNotFoundError,
    ConfigLowerCaseNameError,
    ConfigSectionNotFoundError,
)
from .csv import (
    CsvCellReferenceError,
    CsvError,
    CsvHeadersTooFewError,
    CsvNoDataRowsError,
    CsvRowDuplicateKeyError,
    CsvRowNotFoundError,
    EncodingDetectionError,
)
from .excel import (
    EmptyHeaderCellError,
    ExcelError,
    ExcelFileNotFoundError,
    ExcelHeadersTooFewError,
    FileFormatMismatchError,
    InvalidTableNameError,
    LastSheetDeletionError,
    MacroError,
    RowTransferError,
    SheetAlreadyExistsError,
    SheetNotFoundError,
    TableAlreadyExistsError,
    TableNotFoundError,
)
from .file import UnsupportedFileSuffixError
from .outlook import (
    ClassicOutlookNotAvailableError,
    OutlookAttachmentNotFoundError,
    OutlookError,
    OutlookFolderNotFoundError,
)
from .rpa import (
    RpaError,
    RpaLibraryNotFoundError,
)
from .warning import _warn_coerce as _warn_coerce

__all__ = [
    "ComkenError",
    "AccessError",
    "AccessBackupError",
    "AccessFileNotFoundError",
    "AccessLocalCopyError",
    "AccessRoutineError",
    "AccessSourceNotFoundError",
    "ExcelError",
    "ExcelFileNotFoundError",
    "SheetNotFoundError",
    "SheetAlreadyExistsError",
    "LastSheetDeletionError",
    "InvalidTableNameError",
    "TableAlreadyExistsError",
    "TableNotFoundError",
    "MacroError",
    "RowTransferError",
    "EmptyHeaderCellError",
    "ExcelHeadersTooFewError",
    "FileFormatMismatchError",
    "CsvError",
    "EncodingDetectionError",
    "CsvHeadersTooFewError",
    "CsvNoDataRowsError",
    "CsvRowNotFoundError",
    "CsvRowDuplicateKeyError",
    "CsvCellReferenceError",
    "ColumnNotFoundError",
    "ExcelColumnNotFoundError",
    "CsvColumnNotFoundError",
    "KeyColumnNotFoundError",
    "InvalidColumnError",
    "ConfigError",
    "ConfigFileNotFoundError",
    "ConfigCreatedFromExampleError",
    "ConfigLowerCaseNameError",
    "ConfigSectionNotFoundError",
    "UnsupportedFileSuffixError",
    "OutlookError",
    "ClassicOutlookNotAvailableError",
    "OutlookFolderNotFoundError",
    "OutlookAttachmentNotFoundError",
    "RpaError",
    "RpaLibraryNotFoundError",
    "BrowserError",
    "DriverStartError",
    "BrowsersNotStartedError",
    "BrowsersClosedError",
    "SessionNotStartedError",
    "SessionClosedError",
    "ConcurrentSessionUseError",
    "SessionNameConflictError",
    "SessionNotFoundError",
    "ElementNotFoundError",
    "PopupTabNotOpenedError",
    "DownloadTimeoutError",
]
