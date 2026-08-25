"""comken/exceptions/__init__.py — comken の例外体系。

ComkenError
├── SiteOwnerRequiredError          SiteBase / SalesforceBase に OWNER が未設定
├── InternalLibraryError
│   ├── InternalLibraryNotFoundError         指定した社内ライブラリが見つからない
│   └── InternalLibraryVersionMismatchError  指定したバージョンの社内ライブラリが見つからない
├── LoggingAlreadyConfiguredError   root logger が設定済み
├── LoggingConflictError            root logger に他ライブラリの handler が混ざっている
├── LogRootNotConfiguredError       LoggerSite の LOG_ROOT が未設定
├── UnsupportedFileSuffixError
├── FileDeletionError
├── FileSuffixMissingError
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
│   ├── ExcelSaveValidationError
│   ├── ExcelMacroPreservationError
│   ├── ExcelReadOnlyOperationError
│   ├── SheetNotFoundError
│   ├── SheetAlreadyExistsError
│   ├── SheetNameError
│   ├── InvalidTableNameError
│   ├── TableAlreadyExistsError
│   ├── TableNotFoundError
│   ├── TableFormulaOverwriteError
│   ├── TableColumnMismatchError
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
│   ├── TableRowColumnsError
│   ├── TableTypeConversionError
│   ├── TableNotOpenError
│   └── TransferDestinationMissingError
├── TransferDestinationMultipleMatchError
├── ColumnNotFoundError
│   ├── ExcelColumnNotFoundError
│   └── KeyColumnNotFoundError
├── ConfigError
│   ├── ConfigFileNotFoundError
│   ├── ConfigCreatedFromExampleError
│   ├── ConfigLowerCaseNameError
│   ├── ConfigSectionNotFoundError
│   ├── ConfigKeyNotFoundError
│   └── ConfigMappingEmptyValueError
├── MasterTableError
│   ├── MasterSheetNotDefinedError
│   ├── MasterColumnNotFoundError
│   ├── MasterRowValueError
│   └── MasterDuplicateValueError
├── StateError
│   ├── StateFileCorruptedError
│   ├── StateLowerCaseNameError
│   └── StateValueTypeError
├── WindowNotFoundError
├── HolidayCalendarError
│   ├── HolidayCalendarFetchError
│   ├── HolidayCalendarSourceError
│   │   └── HolidayCalendarFormatError
│   └── BusinessDayNotFoundError
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
│   ├── ScheduledDownloadFailedError
│   ├── UnsupportedScheduleFrequencyError
│   ├── ScheduleIntervalMissingError
│   ├── ScheduleRequiredValueMissingError
│   └── ScheduleWeekdayInvalidError

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
)
from comken.exceptions.config import (
    ConfigCreatedFromExampleError,
    ConfigError,
    ConfigFileNotFoundError,
    ConfigKeyNotFoundError,
    ConfigLowerCaseNameError,
    ConfigMappingEmptyValueError,
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
    ScheduleIntervalMissingError,
    ScheduleRequiredValueMissingError,
    ScheduleWeekdayInvalidError,
    UnsupportedScheduleFrequencyError,
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
    ExcelReadOnlyOperationError,
    ExcelSaveValidationError,
    FileFormatMismatchError,
    InvalidTableNameError,
    MacroError,
    SheetAlreadyExistsError,
    SheetNameError,
    SheetNotFoundError,
    TableAlreadyExistsError,
    TableColumnMismatchError,
    TableFormulaOverwriteError,
    TableNotFoundError,
)
from comken.exceptions.file import (
    FileDeletionError,
    FileSuffixMissingError,
    UnsupportedFileSuffixError,
)
from comken.exceptions.holiday import (
    BusinessDayNotFoundError,
    HolidayCalendarError,
    HolidayCalendarFetchError,
    HolidayCalendarFormatError,
    HolidayCalendarSourceError,
)
from comken.exceptions.logger import (
    LoggingAlreadyConfiguredError,
    LoggingConflictError,
    LogRootNotConfiguredError,
)
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
    TableNotOpenError,
    TableRowColumnsError,
    TableTypeConversionError,
    TransferDestinationMissingError,
    TransferDestinationMultipleMatchError,
)
from comken.exceptions.windows import WindowNotFoundError
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
    "SheetNameError",
    "InvalidTableNameError",
    "TableAlreadyExistsError",
    "TableFormulaOverwriteError",
    "TableColumnMismatchError",
    "TableNotFoundError",
    "MacroError",
    "EmptyHeaderCellError",
    "DuplicateHeaderCellError",
    "EmptyExcelTableError",
    "ExcelHeadersTooFewError",
    "ExcelMacroPreservationError",
    "ExcelReadOnlyOperationError",
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
    "InvalidColumnError",
    "ConfigError",
    "ConfigFileNotFoundError",
    "ConfigCreatedFromExampleError",
    "ConfigLowerCaseNameError",
    "ConfigSectionNotFoundError",
    "ConfigKeyNotFoundError",
    "ConfigMappingEmptyValueError",
    "UnsupportedFileSuffixError",
    "FileDeletionError",
    "FileSuffixMissingError",
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
    "BusinessDayNotFoundError",
    "HolidayCalendarError",
    "HolidayCalendarFetchError",
    "HolidayCalendarSourceError",
    "HolidayCalendarFormatError",
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
    "UnsupportedScheduleFrequencyError",
    "ScheduleIntervalMissingError",
    "ScheduleRequiredValueMissingError",
    "ScheduleWeekdayInvalidError",
    "TransferDestinationMultipleMatchError",
    "TableNotOpenError",
    "TransferDestinationMissingError",
    "TableError",
    "InvalidTableInputError",
    "InvalidTableOperationError",
    "TableColumnNotFoundError",
    "TableDuplicateKeyError",
    "TableRowColumnsError",
    "TableTypeConversionError",
    "LoggingAlreadyConfiguredError",
    "LoggingConflictError",
    "LogRootNotConfiguredError",
    "WindowNotFoundError",
]
