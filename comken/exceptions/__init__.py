"""comken/exceptions/__init__.py — comken の例外体系。

ComkenError
├── SiteOwnerRequiredError          SiteBase / SalesforceBase に OWNER が未設定
├── LoggingAlreadyConfiguredError   root logger が設定済み
├── LoggingConflictError            root logger に他ライブラリの handler が混ざっている
├── LogRootNotConfiguredError       LoggerSite の LOG_ROOT が未設定
├── ComkenFileNotFoundError         ファイルまたはフォルダが見つからない
├── UnsupportedFileSuffixError
├── FileDeletionError
├── FileSuffixMissingError
├── AccessError
│   ├── AccessBackupError
│   ├── AccessLocalCopyError
│   ├── AccessRoutineError
│   └── AccessSourceNotFoundError
├── OutlookError
│   ├── ClassicOutlookNotAvailableError
│   └── OutlookFolderNotFoundError
├── ExcelError
│   ├── ExcelApplicationNotAvailableError
│   ├── SheetNotFoundError
├── CSVError
├── CredentialError
│   ├── InvalidCredentialNameError
│   ├── CredentialNotFoundError
│   ├── CredentialDecryptionError
│   ├── CredentialStoreCorruptedError
│   ├── CredentialImportError
│   └── PasswordRejectedError
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
│   ├── SalesforceSiteSelectionError
│   ├── SalesforceReportExecutionError
│   ├── SalesforceReportAccessDeniedError
│   ├── SalesforceReportExportError
│   ├── SalesforceBulkFailedError
│   └── SalesforceBulkTimeoutError
├── BrowserError
│   ├── DriverStartError
│   ├── BrowserNotStartedError
│   ├── BrowserClosedError
│   ├── ConcurrentSessionUseError
│   ├── SessionNameConflictError
│   ├── SessionNotFoundError
│   ├── SiteConfigError
│   ├── SiteAlreadyInLibraryError
│   ├── ElementNotFoundError
│   ├── PopupTabNotOpenedError
│   ├── DownloadTimeoutError
│   └── LoginFailedError
├── InvalidColumnError
├── TableError
│   ├── InvalidTableInputError
│   ├── TableColumnNotFoundError
│   ├── TableDuplicateKeyError
│   ├── InvalidTableOperationError
│   └── TableNotOpenError
├── ColumnNotFoundError
│   ├── ExcelColumnNotFoundError
│   └── TransferSourceColumnNotFoundError
├── ConfigError
│   ├── ConfigCreatedFromExampleError
│   ├── ConfigLowerCaseNameError
│   ├── ConfigSectionNotFoundError
│   ├── ConfigKeyNotFoundError
│   ├── ConfigMappingEmptyValueError
│   └── ConfigSubclassingNotSupportedError
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
├── CalendarError
│   ├── CalendarFormatError
│   └── BusinessDayNotFoundError
├── DownloaderError
│   ├── HistoryWriteError
│   ├── HistoryLockTimeoutError
│   ├── CachedReportNotFoundError
│   ├── ReportNotRegisteredError
│   ├── SoqlReportNotRegisteredError
│   ├── GroupNotRegisteredError
│   ├── ReportDisabledError
│   ├── EmptyReportError
│   ├── ReportReservePathLimitError
│   ├── ScheduleSettingError
│   ├── ReportFolderNotFoundError
│   ├── ScheduledDownloadFailedError
│   └── SoqlDownloadFailedError
└── DataLoaderError
│   ├── DataLoaderTimeoutError
│   └── DataLoaderExecutionError

カテゴリ基底クラスはまとめて捕捉するために使い、直接送出しない。
"""

from comken.exceptions.access import (
    AccessBackupError,
    AccessError,
    AccessLocalCopyError,
    AccessRoutineError,
    AccessSourceNotFoundError,
)
from comken.exceptions.base import ComkenError, SiteOwnerRequiredError
from comken.exceptions.browser import (
    BrowserClosedError,
    BrowserError,
    BrowserNotStartedError,
    ConcurrentSessionUseError,
    DownloadTimeoutError,
    DriverStartError,
    ElementNotFoundError,
    LoginFailedError,
    PopupTabNotOpenedError,
    SessionNameConflictError,
    SessionNotFoundError,
    SiteAlreadyInLibraryError,
    SiteConfigError,
)
from comken.exceptions.calendar import (
    BusinessDayNotFoundError,
    CalendarError,
    CalendarFormatError,
)
from comken.exceptions.column import (
    ColumnNotFoundError,
    ExcelColumnNotFoundError,
    InvalidColumnError,
    TransferSourceColumnNotFoundError,
)
from comken.exceptions.config import (
    ConfigCreatedFromExampleError,
    ConfigError,
    ConfigKeyNotFoundError,
    ConfigLowerCaseNameError,
    ConfigMappingEmptyValueError,
    ConfigSectionNotFoundError,
    ConfigSubclassingNotSupportedError,
)
from comken.exceptions.credential import (
    CredentialDecryptionError,
    CredentialError,
    CredentialImportError,
    CredentialNotFoundError,
    CredentialStoreCorruptedError,
    InvalidCredentialNameError,
    PasswordRejectedError,
)
from comken.exceptions.csv import CSVError
from comken.exceptions.dataloader import (
    DataLoaderError,
    DataLoaderExecutionError,
    DataLoaderTimeoutError,
)
from comken.exceptions.downloader import (
    CachedReportNotFoundError,
    DownloaderError,
    EmptyReportError,
    GroupNotRegisteredError,
    HistoryLockTimeoutError,
    HistoryWriteError,
    ReportDisabledError,
    ReportFolderNotFoundError,
    ReportNotRegisteredError,
    ReportReservePathLimitError,
    ScheduledDownloadFailedError,
    ScheduleSettingError,
    SoqlDownloadFailedError,
    SoqlReportNotRegisteredError,
)
from comken.exceptions.excel import (
    ExcelApplicationNotAvailableError,
    ExcelError,
    SheetNotFoundError,
)
from comken.exceptions.file import (
    ComkenFileNotFoundError,
    FileDeletionError,
    FileSuffixMissingError,
    UnsupportedFileSuffixError,
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
    OutlookError,
    OutlookFolderNotFoundError,
)
from comken.exceptions.salesforce import (
    SalesforceAuthError,
    SalesforceBulkFailedError,
    SalesforceBulkTimeoutError,
    SalesforceConnectionError,
    SalesforceCredentialRotationError,
    SalesforceError,
    SalesforceExternalIDMissingError,
    SalesforceReportAccessDeniedError,
    SalesforceReportExecutionError,
    SalesforceReportExportError,
    SalesforceReportFormatError,
    SalesforceReportIDNotFoundError,
    SalesforceReportTruncatedError,
    SalesforceRequestError,
    SalesforceSiteNotFoundError,
    SalesforceSiteSelectionError,
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
)
from comken.exceptions.windows import WindowNotFoundError

__all__ = [
    "ComkenError",
    "SiteOwnerRequiredError",
    "AccessError",
    "AccessBackupError",
    "AccessLocalCopyError",
    "AccessRoutineError",
    "AccessSourceNotFoundError",
    "ExcelError",
    "ExcelApplicationNotAvailableError",
    "SheetNotFoundError",
    "CSVError",
    "ColumnNotFoundError",
    "ExcelColumnNotFoundError",
    "TransferSourceColumnNotFoundError",
    "InvalidColumnError",
    "ConfigError",
    "ConfigCreatedFromExampleError",
    "ConfigLowerCaseNameError",
    "ConfigSectionNotFoundError",
    "ConfigKeyNotFoundError",
    "ConfigMappingEmptyValueError",
    "ConfigSubclassingNotSupportedError",
    "ComkenFileNotFoundError",
    "UnsupportedFileSuffixError",
    "FileDeletionError",
    "FileSuffixMissingError",
    "OutlookError",
    "ClassicOutlookNotAvailableError",
    "OutlookFolderNotFoundError",
    "CredentialError",
    "InvalidCredentialNameError",
    "CredentialNotFoundError",
    "CredentialDecryptionError",
    "CredentialStoreCorruptedError",
    "CredentialImportError",
    "PasswordRejectedError",
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
    "SalesforceReportAccessDeniedError",
    "SalesforceReportExportError",
    "SalesforceSiteNotFoundError",
    "SalesforceSiteSelectionError",
    "SalesforceBulkFailedError",
    "SalesforceBulkTimeoutError",
    "BrowserError",
    "DriverStartError",
    "BrowserNotStartedError",
    "BrowserClosedError",
    "ConcurrentSessionUseError",
    "SessionNameConflictError",
    "SessionNotFoundError",
    "SiteConfigError",
    "SiteAlreadyInLibraryError",
    "ElementNotFoundError",
    "PopupTabNotOpenedError",
    "DownloadTimeoutError",
    "LoginFailedError",
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
    "CalendarError",
    "CalendarFormatError",
    "DownloaderError",
    "HistoryWriteError",
    "HistoryLockTimeoutError",
    "CachedReportNotFoundError",
    "ReportNotRegisteredError",
    "SoqlReportNotRegisteredError",
    "GroupNotRegisteredError",
    "ReportDisabledError",
    "EmptyReportError",
    "ReportFolderNotFoundError",
    "ReportReservePathLimitError",
    "ScheduleSettingError",
    "ScheduledDownloadFailedError",
    "SoqlDownloadFailedError",
    "DataLoaderError",
    "DataLoaderTimeoutError",
    "DataLoaderExecutionError",
    "InvalidTableOperationError",
    "TableNotOpenError",
    "TableError",
    "InvalidTableInputError",
    "TableColumnNotFoundError",
    "TableDuplicateKeyError",
    "LoggingAlreadyConfiguredError",
    "LoggingConflictError",
    "LogRootNotConfiguredError",
    "WindowNotFoundError",
]
