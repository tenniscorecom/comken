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
│   ├── SalesforceRequestError
│   ├── SalesforceReportTruncatedError
│   └── SalesforceReportIDNotFoundError
├── BrowserError
│   ├── ElementNotFoundError
│   └── LoginFailedError
├── InvalidColumnError
├── TableError
│   ├── InvalidTableInputError
│   ├── TableColumnNotFoundError
│   └── TableDuplicateKeyError
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
│   ├── EmptyReportError
│   ├── ReportReservePathLimitError
│   ├── ReportFolderNotFoundError
│   └── ScheduledDownloadFailedError
└── DataLoaderError

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
from comken.exceptions.browser import BrowserError, ElementNotFoundError, LoginFailedError
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
from comken.exceptions.dataloader import DataLoaderError
from comken.exceptions.downloader import (
    CachedReportNotFoundError,
    DownloaderError,
    EmptyReportError,
    GroupNotRegisteredError,
    HistoryLockTimeoutError,
    HistoryWriteError,
    ReportFolderNotFoundError,
    ReportNotRegisteredError,
    ReportReservePathLimitError,
    ScheduledDownloadFailedError,
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
    MasterDuplicateValueError,
    MasterRowValueError,
    MasterTableError,
)
from comken.exceptions.outlook import (
    ClassicOutlookNotAvailableError,
    OutlookError,
    OutlookFolderNotFoundError,
)
from comken.exceptions.salesforce import (
    SalesforceAuthError,
    SalesforceError,
    SalesforceReportIDNotFoundError,
    SalesforceReportTruncatedError,
    SalesforceRequestError,
)
from comken.exceptions.state import (
    StateError,
    StateFileCorruptedError,
    StateLowerCaseNameError,
    StateValueTypeError,
)
from comken.exceptions.table import (
    InvalidTableInputError,
    TableColumnNotFoundError,
    TableDuplicateKeyError,
    TableError,
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
    "SalesforceRequestError",
    "SalesforceReportTruncatedError",
    "SalesforceReportIDNotFoundError",
    "BrowserError",
    "ElementNotFoundError",
    "LoginFailedError",
    "MasterTableError",
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
    "EmptyReportError",
    "ReportFolderNotFoundError",
    "ReportReservePathLimitError",
    "ScheduledDownloadFailedError",
    "DataLoaderError",
    "TableError",
    "InvalidTableInputError",
    "TableColumnNotFoundError",
    "TableDuplicateKeyError",
    "LoggingAlreadyConfiguredError",
    "LoggingConflictError",
    "LogRootNotConfiguredError",
    "WindowNotFoundError",
]
