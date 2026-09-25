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
└── DataLoaderError

カテゴリ基底クラスはまとめて捕捉するために使い、直接送出しない。
"""

from comken.exceptions.access import AccessError
from comken.exceptions.base import ComkenError, SiteOwnerRequiredError
from comken.exceptions.browser import BrowserError, ElementNotFoundError, LoginFailedError
from comken.exceptions.calendar import HolidayError, WorkdayNotFoundError
from comken.exceptions.column import (
    ColumnNotFoundError,
    ExcelColumnNotFoundError,
    InvalidColumnError,
    TransferSourceColumnNotFoundError,
)
from comken.exceptions.config import ConfigError, ConfigKeyNotFoundError
from comken.exceptions.credential import (
    CredentialError,
    CredentialNotFoundError,
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
from comken.exceptions.outlook import OutlookError
from comken.exceptions.salesforce import (
    SalesforceAuthError,
    SalesforceError,
    SalesforceReportIDNotFoundError,
    SalesforceReportTruncatedError,
    SalesforceRequestError,
)
from comken.exceptions.state import StateError
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
