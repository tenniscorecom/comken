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
├── OutlookError
├── ExcelError
│   ├── ExcelApplicationNotAvailableError
│   ├── SheetNotFoundError
├── CSVError
├── CredentialError
│   ├── CredentialNotFoundError
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
│   └── ConfigKeyNotFoundError
├── MasterTableError
│   ├── MasterRowValueError
│   └── MasterDuplicateValueError
├── StateError
├── WindowNotFoundError
├── HolidayError
│   └── WorkdayNotFoundError
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

カテゴリ基底クラスはまとめて捕捉するために使い、直接送出しない。
"""

from comken.exceptions.base import ComkenError, SiteOwnerRequiredError
from comken.exceptions.config import (
    ConfigError,
    ConfigKeyNotFoundError,
    CredentialError,
    CredentialNotFoundError,
    PasswordRejectedError,
)
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
from comken.exceptions.files import (
    ComkenFileNotFoundError,
    CSVError,
    FileDeletionError,
    FileSuffixMissingError,
    LoggingAlreadyConfiguredError,
    LoggingConflictError,
    LogRootNotConfiguredError,
    StateError,
    UnsupportedFileSuffixError,
)
from comken.exceptions.holidays import HolidayError, WorkdayNotFoundError
from comken.exceptions.office import (
    AccessError,
    ExcelApplicationNotAvailableError,
    ExcelError,
    OutlookError,
    SheetNotFoundError,
    WindowNotFoundError,
)
from comken.exceptions.tables import (
    ColumnNotFoundError,
    ExcelColumnNotFoundError,
    InvalidColumnError,
    InvalidTableInputError,
    MasterDuplicateValueError,
    MasterRowValueError,
    MasterTableError,
    TableColumnNotFoundError,
    TableDuplicateKeyError,
    TableError,
    TransferSourceColumnNotFoundError,
)
from comken.exceptions.web import (
    BrowserError,
    ElementNotFoundError,
    LoginFailedError,
    SalesforceAuthError,
    SalesforceError,
    SalesforceReportIDNotFoundError,
    SalesforceReportTruncatedError,
    SalesforceRequestError,
)

__all__ = [
    "ComkenError",
    "SiteOwnerRequiredError",
    "AccessError",
    "ExcelError",
    "ExcelApplicationNotAvailableError",
    "SheetNotFoundError",
    "CSVError",
    "ColumnNotFoundError",
    "ExcelColumnNotFoundError",
    "TransferSourceColumnNotFoundError",
    "InvalidColumnError",
    "ConfigError",
    "ConfigKeyNotFoundError",
    "ComkenFileNotFoundError",
    "UnsupportedFileSuffixError",
    "FileDeletionError",
    "FileSuffixMissingError",
    "OutlookError",
    "CredentialError",
    "CredentialNotFoundError",
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
    "HolidayError",
    "WorkdayNotFoundError",
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
    "TableError",
    "InvalidTableInputError",
    "TableColumnNotFoundError",
    "TableDuplicateKeyError",
    "LoggingAlreadyConfiguredError",
    "LoggingConflictError",
    "LogRootNotConfiguredError",
    "WindowNotFoundError",
]
