"""comken/exceptions/__init__.py — comken の例外体系。

ComkenError
├── SiteOwnerRequiredError          SiteBase / SalesforceBase に OWNER が未設定
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
│   ├── TableNotAvailableInReadOnlyError
│   ├── MacroError
│   ├── EmptyHeaderCellError
│   ├── DuplicateHeaderCellError
│   ├── EmptyExcelTableError
│   ├── ExcelHeadersTooFewError
│   └── FileFormatMismatchError
├── CsvError
│   ├── EncodingDetectionError
│   ├── CsvFileNotFoundError
│   ├── CsvHeaderMissingError
│   ├── CsvInvalidHeaderError
│   ├── CsvRowLengthError
│   └── CsvColumnsRequiredError
├── RpaError
│   └── RpaLibraryNotFoundError
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
│   ├── SalesforceExternalIdMissingError
│   ├── SalesforceCredentialRotationError
│   ├── SalesforceReportTruncatedError
│   ├── SalesforceReportFormatError
│   ├── SalesforceReportIdNotFoundError
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
│   └── TableTypeConversionError
├── TransferDestinationRowMissingError
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
│   ├── InvalidReportUrlError
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
    CsvColumnsRequiredError,
    CsvError,
    CsvFileNotFoundError,
    CsvHeaderMissingError,
    CsvInvalidHeaderError,
    CsvRowLengthError,
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
    InvalidReportUrlError,
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
    TableNotAvailableInReadOnlyError,
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
from comken.exceptions.rpa import RpaError, RpaLibraryNotFoundError
from comken.exceptions.salesforce import (
    SalesforceAuthError,
    SalesforceConnectionError,
    SalesforceCredentialRotationError,
    SalesforceError,
    SalesforceExternalIdMissingError,
    SalesforceReportExecutionError,
    SalesforceReportFormatError,
    SalesforceReportIdNotFoundError,
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
    TransferDestinationMultipleMatchError,
    TransferDestinationRowMissingError,
)

__all__ = [
    "ComkenError",
    "SiteOwnerRequiredError",
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
    "TableNotAvailableInReadOnlyError",
    "MacroError",
    "EmptyHeaderCellError",
    "DuplicateHeaderCellError",
    "EmptyExcelTableError",
    "ExcelHeadersTooFewError",
    "ExcelMacroPreservationError",
    "ExcelSaveNotCompletedError",
    "ExcelSaveValidationError",
    "FileFormatMismatchError",
    "CsvError",
    "EncodingDetectionError",
    "CsvFileNotFoundError",
    "CsvHeaderMissingError",
    "CsvInvalidHeaderError",
    "CsvRowLengthError",
    "CsvColumnsRequiredError",
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
    "RpaError",
    "RpaLibraryNotFoundError",
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
    "SalesforceExternalIdMissingError",
    "SalesforceCredentialRotationError",
    "SalesforceReportTruncatedError",
    "SalesforceReportFormatError",
    "SalesforceReportIdNotFoundError",
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
    "InvalidReportUrlError",
    "EmptyReportError",
    "ReportFolderNotFoundError",
    "ScheduledDownloadFailedError",
    "TransferDestinationRowMissingError",
    "TransferDestinationMultipleMatchError",
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
