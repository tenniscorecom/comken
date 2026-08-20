"""comken/exceptions/__init__.py — comken の例外体系。

ComkenError
├── SiteOwnerRequiredError          SiteBase / SalesforceBase に OWNER が未設定
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
│   ├── ExcelFileNotFoundError
│   ├── ExcelApplicationNotAvailableError
│   ├── ExcelSaveNotCompletedError
│   ├── SheetNotFoundError
│   ├── SheetAlreadyExistsError
│   ├── LastSheetDeletionError
│   ├── InvalidTableNameError
│   ├── TableAlreadyExistsError
│   ├── TableNotFoundError
│   ├── TableNotAvailableInReadOnlyError
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
├── ColumnNotFoundError
│   ├── ExcelColumnNotFoundError
│   ├── CsvColumnNotFoundError
│   ├── KeyColumnNotFoundError
│   ├── TransferKeyColumnNotFoundError
│   ├── TransferDestinationColumnNotFoundError
│   └── TransferSourceColumnNotFoundError
├── ConfigError
│   ├── ConfigFileNotFoundError
│   ├── ConfigCreatedFromExampleError
│   ├── ConfigLowerCaseNameError
│   ├── ConfigRequiredKeysMissingError
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
│   ├── ReportNotRegisteredError
│   ├── ReportDisabledError
│   ├── InvalidReportUrlError
│   ├── ScheduledReportNotRegisteredError
│   ├── ScheduledReportNotDownloadedError
│   ├── ReportFileMissingError
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
    CsvColumnNotFoundError,
    ExcelColumnNotFoundError,
    InvalidColumnError,
    KeyColumnNotFoundError,
    TransferDestinationColumnNotFoundError,
    TransferKeyColumnNotFoundError,
    TransferSourceColumnNotFoundError,
)
from comken.exceptions.config import (
    ConfigCreatedFromExampleError,
    ConfigError,
    ConfigFileNotFoundError,
    ConfigKeyNotFoundError,
    ConfigLowerCaseNameError,
    ConfigRequiredKeysMissingError,
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
    CsvCellReferenceError,
    CsvError,
    CsvHeadersTooFewError,
    CsvNoDataRowsError,
    CsvRowDuplicateKeyError,
    CsvRowNotFoundError,
    EncodingDetectionError,
)
from comken.exceptions.downloader import (
    DownloaderError,
    EmptyReportError,
    InvalidReportUrlError,
    ReportDisabledError,
    ReportFileMissingError,
    ReportFolderNotFoundError,
    ReportNotRegisteredError,
    ScheduledDownloadFailedError,
    ScheduledReportNotDownloadedError,
    ScheduledReportNotRegisteredError,
)
from comken.exceptions.excel import (
    EmptyHeaderCellError,
    ExcelApplicationNotAvailableError,
    ExcelError,
    ExcelFileNotFoundError,
    ExcelHeadersTooFewError,
    ExcelSaveNotCompletedError,
    FileFormatMismatchError,
    InvalidTableNameError,
    LastSheetDeletionError,
    MacroError,
    RowTransferError,
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
from comken.exceptions.warning import _warn_coerce as _warn_coerce

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
    "RowTransferError",
    "EmptyHeaderCellError",
    "ExcelHeadersTooFewError",
    "ExcelSaveNotCompletedError",
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
    "TransferKeyColumnNotFoundError",
    "TransferDestinationColumnNotFoundError",
    "TransferSourceColumnNotFoundError",
    "InvalidColumnError",
    "ConfigError",
    "ConfigFileNotFoundError",
    "ConfigCreatedFromExampleError",
    "ConfigLowerCaseNameError",
    "ConfigRequiredKeysMissingError",
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
    "ReportNotRegisteredError",
    "ReportDisabledError",
    "InvalidReportUrlError",
    "ScheduledReportNotRegisteredError",
    "ScheduledReportNotDownloadedError",
    "ReportFileMissingError",
    "EmptyReportError",
    "ReportFolderNotFoundError",
    "ScheduledDownloadFailedError",
]
