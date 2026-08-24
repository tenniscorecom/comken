"""comken/exceptions/__init__.py — comken の例外体系。

ComkenError
├── SiteOwnerRequiredError          SiteBase / SalesforceBase に OWNER が未設定
├── InternalLibraryError
│   ├── InternalLibraryNotFoundError         指定した社内ライブラリが見つからない
│   └── InternalLibraryVersionMismatchError  指定したバージョンの社内ライブラリが見つからない
│
│   旧 RPA 例外名は ``__getattr__`` シム経由で新例外と同一クラスとして公開する
│   （``RpaError is InternalLibraryError`` などの別名）。 旧名・別名の関係であって
│   継承関係ではないため、上のツリーには載せない（同じクラスを二重に並べると
│   親子に見えてしまうため）。 旧名は SUPPLEMENTAL_ERRORS 側で別表として記載する。
├── LoggingAlreadyConfiguredError   root logger が設定済み
├── LoggerHostNotConfiguredError     実行端末のログ保存先が未登録
├── UnsupportedFileSuffixError
├── FileDeletionError
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
│   ├── DataSheetAccessError
│   ├── ExcelFileNotFoundError
│   ├── ExcelApplicationNotAvailableError
│   ├── ExcelSaveNotCompletedError
│   ├── ExcelSaveValidationError
│   ├── ExcelMacroPreservationError
│   ├── SheetNotFoundError
│   ├── SheetAlreadyExistsError
│   ├── LastSheetDeletionError
│   ├── InvalidTableNameError
│   ├── TableAlreadyExistsError
│   ├── TableNotFoundError
│   ├── MacroError
│   ├── EmptyHeaderCellError
│   ├── DuplicateHeaderCellError
│   ├── EmptyExcelTableError
│   ├── ExcelHeadersTooFewError
│   └── FileFormatMismatchError
├── CSVError
│   ├── EncodingDetectionError
│   ├── CSVFileNotFoundError
│   ├── CSVHeaderMissingError
│   ├── CSVInvalidHeaderError
│   ├── CSVRowLengthError
│   └── CSVColumnsRequiredError
├── CredentialError
│   ├── InvalidCredentialNameError
│   ├── CredentialNotFoundError
│   ├── CredentialDecryptionError
│   ├── CredentialStoreCorruptedError
│   └── CredentialImportError
├── SalesforceError
│   ├── SalesforceAuthError
│   ├── SalesforceConnectionError
│   ├── SalesforceRequestError
│   ├── SalesforceExternalIDMissingError
│   ├── SalesforceCredentialRotationError
│   ├── SalesforceReportTruncatedError
│   ├── SalesforceReportFormatError
│   ├── SalesforceReportIDNotFoundError
│   ├── SalesforceSiteNotFoundError
│   └── SalesforceReportExecutionError
├── BrowserError
│   ├── DriverStartError
│   ├── BrowsersNotStartedError
│   ├── BrowsersClosedError
│   ├── SessionNotStartedError
│   ├── SessionClosedError
│   ├── ConcurrentSessionUseError
│   ├── SessionNameConflictError
│   ├── SessionNotFoundError
│   ├── SiteConfigError
│   ├── SiteAlreadyInLibraryError
│   ├── SiteNotStartedError
│   ├── ElementNotFoundError
│   ├── PopupTabNotOpenedError
│   └── DownloadTimeoutError
├── InvalidColumnError
├── TableError
│   ├── InvalidTableInputError
│   ├── InvalidTableOperationError
│   ├── TableColumnNotFoundError
│   ├── TableDuplicateKeyError
│   ├── TableMergeColumnCollisionError
│   ├── TableMergeSuffixError
│   ├── TableRowColumnsError
│   ├── TableTypeConversionError
│   └── TransferDestinationMissingError
├── TransferDestinationMultipleMatchError
├── ColumnNotFoundError
│   ├── ExcelColumnNotFoundError
│   ├── KeyColumnNotFoundError
│   └── TransferSourceColumnNotFoundError
├── ConfigError
│   ├── ConfigFileNotFoundError
│   ├── ConfigCreatedFromExampleError
│   ├── ConfigLowerCaseNameError
│   ├── ConfigSectionNotFoundError
│   └── ConfigKeyNotFoundError
├── MasterTableError
│   ├── MasterSheetNotDefinedError
│   ├── MasterColumnNotFoundError
│   ├── MasterRowValueError
│   └── MasterDuplicateValueError
├── StateError
│   ├── StateFileCorruptedError
│   ├── StateLowerCaseNameError
│   └── StateValueTypeError
├── HolidayCalendarError
│   ├── HolidayCalendarFetchError
│   ├── HolidayCalendarSourceError
│   │   └── HolidayCalendarFormatError
│   └── HolidayCalendarExpiredError
└── DownloaderError
│   ├── HistoryWriteError
│   ├── HistoryLockTimeoutError
│   ├── HistoryHeaderMismatchError
│   ├── CachedReportNotFoundError
│   ├── CachedReportNotRegisteredError
│   ├── ReportNotRegisteredError
│   ├── ReportDisabledError
│   ├── InvalidReportURLError
│   ├── EmptyReportError
│   ├── ReportFolderNotFoundError
│   └── ScheduledDownloadFailedError

カテゴリ基底クラスはまとめて捕捉するために使い、直接送出しない。
"""

from comken.exceptions.access import (
    AccessBackupError,
    AccessError,
    AccessFileNotFoundError,
    AccessLocalCopyError,
    AccessRoutineError,
    AccessSourceNotFoundError,
)
from comken.exceptions.base import ComkenError, SiteOwnerRequiredError
from comken.exceptions.browser import (
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
    SiteAlreadyInLibraryError,
    SiteConfigError,
    SiteNotStartedError,
)
from comken.exceptions.column import (
    ColumnNotFoundError,
    ExcelColumnNotFoundError,
    InvalidColumnError,
    KeyColumnNotFoundError,
    TransferSourceColumnNotFoundError,
)
from comken.exceptions.config import (
    ConfigCreatedFromExampleError,
    ConfigError,
    ConfigFileNotFoundError,
    ConfigKeyNotFoundError,
    ConfigLowerCaseNameError,
    ConfigSectionNotFoundError,
)
from comken.exceptions.credential import (
    CredentialDecryptionError,
    CredentialError,
    CredentialImportError,
    CredentialNotFoundError,
    CredentialStoreCorruptedError,
    InvalidCredentialNameError,
)
from comken.exceptions.csv import (
    CSVColumnsRequiredError,
    CSVError,
    CSVFileNotFoundError,
    CSVHeaderMissingError,
    CSVInvalidHeaderError,
    CSVRowLengthError,
    EncodingDetectionError,
)
from comken.exceptions.downloader import (
    CachedReportNotFoundError,
    CachedReportNotRegisteredError,
    DownloaderError,
    EmptyReportError,
    HistoryHeaderMismatchError,
    HistoryLockTimeoutError,
    HistoryWriteError,
    InvalidReportURLError,
    ReportDisabledError,
    ReportFolderNotFoundError,
    ReportNotRegisteredError,
    ScheduledDownloadFailedError,
)
from comken.exceptions.excel import (
    DataSheetAccessError,
    DuplicateHeaderCellError,
    EmptyExcelTableError,
    EmptyHeaderCellError,
    ExcelApplicationNotAvailableError,
    ExcelError,
    ExcelFileNotFoundError,
    ExcelHeadersTooFewError,
    ExcelMacroPreservationError,
    ExcelSaveNotCompletedError,
    ExcelSaveValidationError,
    FileFormatMismatchError,
    InvalidTableNameError,
    LastSheetDeletionError,
    MacroError,
    SheetAlreadyExistsError,
    SheetNotFoundError,
    TableAlreadyExistsError,
    TableNotFoundError,
)
from comken.exceptions.file import FileDeletionError, UnsupportedFileSuffixError
from comken.exceptions.holiday import (
    HolidayCalendarError,
    HolidayCalendarExpiredError,
    HolidayCalendarFetchError,
    HolidayCalendarFormatError,
    HolidayCalendarSourceError,
)
from comken.exceptions.logger import LoggerHostNotConfiguredError, LoggingAlreadyConfiguredError
from comken.exceptions.master_table import (
    MasterColumnNotFoundError,
    MasterDuplicateValueError,
    MasterRowValueError,
    MasterSheetNotDefinedError,
    MasterTableError,
)
from comken.exceptions.outlook import (
    ClassicOutlookNotAvailableError,
    OutlookAttachmentNotFoundError,
    OutlookError,
    OutlookFolderNotFoundError,
)
from comken.exceptions.salesforce import (
    SalesforceAuthError,
    SalesforceConnectionError,
    SalesforceCredentialRotationError,
    SalesforceError,
    SalesforceExternalIDMissingError,
    SalesforceReportExecutionError,
    SalesforceReportFormatError,
    SalesforceReportIDNotFoundError,
    SalesforceReportTruncatedError,
    SalesforceRequestError,
    SalesforceSiteNotFoundError,
)
from comken.exceptions.state import (
    StateError,
    StateFileCorruptedError,
    StateLowerCaseNameError,
    StateValueTypeError,
)
from comken.exceptions.table import (
    InvalidTableInputError,
    InvalidTableOperationError,
    TableColumnNotFoundError,
    TableDuplicateKeyError,
    TableError,
    TableMergeColumnCollisionError,
    TableMergeSuffixError,
    TableRowColumnsError,
    TableTypeConversionError,
    TransferDestinationMissingError,
    TransferDestinationMultipleMatchError,
)
from comken.internal.exceptions import (
    InternalLibraryError,
    InternalLibraryNotFoundError,
    InternalLibraryVersionMismatchError,
)

__all__ = [
    "ComkenError",
    "SiteOwnerRequiredError",
    "InternalLibraryError",
    "InternalLibraryNotFoundError",
    "InternalLibraryVersionMismatchError",
    # 旧 RPA 例外名（``RpaError`` 等）は ``__getattr__`` シムで取得できるが、
    # 新例外と同一クラス（別名）のため ``__all__`` には載せない。 載せると同じ
    # クラスを二重に並べることになり、ドキュメント生成・``from ... import *``
    # 経由で重複が見える。 旧名は SUPPLEMENTAL_ERRORS 側で別表として記載する。
    "AccessError",
    "AccessBackupError",
    "AccessFileNotFoundError",
    "AccessLocalCopyError",
    "AccessRoutineError",
    "AccessSourceNotFoundError",
    "ExcelError",
    "DataSheetAccessError",
    "ExcelFileNotFoundError",
    "ExcelApplicationNotAvailableError",
    "SheetNotFoundError",
    "SheetAlreadyExistsError",
    "LastSheetDeletionError",
    "InvalidTableNameError",
    "TableAlreadyExistsError",
    "TableNotFoundError",
    "MacroError",
    "EmptyHeaderCellError",
    "DuplicateHeaderCellError",
    "EmptyExcelTableError",
    "ExcelHeadersTooFewError",
    "ExcelMacroPreservationError",
    "ExcelSaveNotCompletedError",
    "ExcelSaveValidationError",
    "FileFormatMismatchError",
    "CSVError",
    "EncodingDetectionError",
    "CSVFileNotFoundError",
    "CSVHeaderMissingError",
    "CSVInvalidHeaderError",
    "CSVRowLengthError",
    "CSVColumnsRequiredError",
    "ColumnNotFoundError",
    "ExcelColumnNotFoundError",
    "KeyColumnNotFoundError",
    "TransferSourceColumnNotFoundError",
    "InvalidColumnError",
    "ConfigError",
    "ConfigFileNotFoundError",
    "ConfigCreatedFromExampleError",
    "ConfigLowerCaseNameError",
    "ConfigSectionNotFoundError",
    "ConfigKeyNotFoundError",
    "UnsupportedFileSuffixError",
    "FileDeletionError",
    "OutlookError",
    "ClassicOutlookNotAvailableError",
    "OutlookFolderNotFoundError",
    "OutlookAttachmentNotFoundError",
    "CredentialError",
    "InvalidCredentialNameError",
    "CredentialNotFoundError",
    "CredentialDecryptionError",
    "CredentialStoreCorruptedError",
    "CredentialImportError",
    "SalesforceError",
    "SalesforceAuthError",
    "SalesforceConnectionError",
    "SalesforceRequestError",
    "SalesforceExternalIDMissingError",
    "SalesforceCredentialRotationError",
    "SalesforceReportTruncatedError",
    "SalesforceReportFormatError",
    "SalesforceReportIDNotFoundError",
    "SalesforceReportExecutionError",
    "SalesforceSiteNotFoundError",
    "BrowserError",
    "DriverStartError",
    "BrowsersNotStartedError",
    "BrowsersClosedError",
    "SessionNotStartedError",
    "SessionClosedError",
    "ConcurrentSessionUseError",
    "SessionNameConflictError",
    "SessionNotFoundError",
    "SiteConfigError",
    "SiteAlreadyInLibraryError",
    "SiteNotStartedError",
    "ElementNotFoundError",
    "PopupTabNotOpenedError",
    "DownloadTimeoutError",
    "MasterTableError",
    "MasterSheetNotDefinedError",
    "MasterColumnNotFoundError",
    "MasterRowValueError",
    "MasterDuplicateValueError",
    "StateError",
    "StateFileCorruptedError",
    "StateLowerCaseNameError",
    "StateValueTypeError",
    "HolidayCalendarError",
    "HolidayCalendarFetchError",
    "HolidayCalendarSourceError",
    "HolidayCalendarFormatError",
    "HolidayCalendarExpiredError",
    "DownloaderError",
    "HistoryWriteError",
    "HistoryLockTimeoutError",
    "HistoryHeaderMismatchError",
    "CachedReportNotFoundError",
    "CachedReportNotRegisteredError",
    "ReportNotRegisteredError",
    "ReportDisabledError",
    "InvalidReportURLError",
    "EmptyReportError",
    "ReportFolderNotFoundError",
    "ScheduledDownloadFailedError",
    "TransferDestinationMultipleMatchError",
    "TransferDestinationMissingError",
    "TableError",
    "InvalidTableInputError",
    "InvalidTableOperationError",
    "TableColumnNotFoundError",
    "TableDuplicateKeyError",
    "TableMergeColumnCollisionError",
    "TableMergeSuffixError",
    "TableRowColumnsError",
    "TableTypeConversionError",
    "LoggingAlreadyConfiguredError",
    "LoggerHostNotConfiguredError",
]


# 旧 RPA 例外名はここで遅延解決する。 import comken.exceptions だけでは
# 警告を出さず、 ``comken.exceptions.RpaError`` のように名前を取り出したときだけ
# ``comken.exceptions.rpa.__getattr__`` が FutureWarning を発する。
def __getattr__(name: str) -> object:
    """旧 RPA 例外名を遅延 import する。"""
    if name in {"RpaError", "RpaLibraryNotFoundError", "RpaLibraryVersionMismatchError"}:
        from comken.exceptions import rpa as _rpa_shim  # 遅延 import: import 時警告を防ぐ

        return getattr(_rpa_shim, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
