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
│   ├── DataSheetAccessError
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
│   ├── CSVHeaderMissingError
│   ├── CSVInvalidHeaderError
│   ├── CSVRowLengthError
│   └── CSVColumnsRequiredError
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
│   ├── SalesforceBulkQueryFailedError
│   ├── SalesforceBulkQueryTimeoutError
│   ├── SalesforceBulkIngestFailedError
│   └── SalesforceBulkIngestTimeoutError
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
│   ├── DownloadTimeoutError
│   └── LoginFailedError
├── InvalidColumnError
├── TableError
│   ├── InvalidTableInputError
│   ├── InvalidTableOperationError
│   ├── TableColumnNotFoundError
│   ├── TableDuplicateKeyError
│   ├── TableRowColumnsError
│   ├── TableTypeConversionError
│   ├── TableNotOpenError
│   ├── TransferDestinationMissingError
│   └── TransferDestinationMultipleMatchError
├── ColumnNotFoundError
│   ├── ExcelColumnNotFoundError
│   ├── KeyColumnNotFoundError
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
│   ├── InvalidReportURLError
│   ├── EmptyReportError
│   ├── ReportReservePathLimitError
│   ├── ScheduledDownloadFailedError
│   ├── SoqlDownloadFailedError
│   ├── UnsupportedScheduleFrequencyError
│   └── ScheduleWeekdayInvalidError
└── DataLoaderError
│   ├── DataLoaderTimeoutError
│   └── DataLoaderExecutionError

カテゴリ基底クラスはまとめて捕捉するために使い、直接送出しない。
"""

import warnings

from comken.exceptions.access import (
    AccessBackupError,
    AccessError,
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
    LoginFailedError,
    PopupTabNotOpenedError,
    SessionClosedError,
    SessionNameConflictError,
    SessionNotFoundError,
    SessionNotStartedError,
    SiteAlreadyInLibraryError,
    SiteConfigError,
    SiteNotStartedError,
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
    KeyColumnNotFoundError,
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
from comken.exceptions.csv import (
    CSVColumnsRequiredError,
    CSVError,
    CSVHeaderMissingError,
    CSVInvalidHeaderError,
    CSVRowLengthError,
    EncodingDetectionError,
)
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
    InvalidReportURLError,
    ReportDisabledError,
    ReportNotRegisteredError,
    ReportReservePathLimitError,
    ScheduledDownloadFailedError,
    ScheduleWeekdayInvalidError,
    SoqlDownloadFailedError,
    SoqlReportNotRegisteredError,
    UnsupportedScheduleFrequencyError,
)
from comken.exceptions.excel import (
    DataSheetAccessError,
    DuplicateHeaderCellError,
    EmptyExcelTableError,
    EmptyHeaderCellError,
    ExcelApplicationNotAvailableError,
    ExcelError,
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
    SalesforceBulkIngestFailedError,
    SalesforceBulkIngestTimeoutError,
    SalesforceBulkQueryFailedError,
    SalesforceBulkQueryTimeoutError,
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
    TableRowColumnsError,
    TableTypeConversionError,
    TransferDestinationMissingError,
    TransferDestinationMultipleMatchError,
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
    "DataSheetAccessError",
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
    "SalesforceBulkQueryFailedError",
    "SalesforceBulkQueryTimeoutError",
    "SalesforceBulkIngestFailedError",
    "SalesforceBulkIngestTimeoutError",
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
    "InvalidReportURLError",
    "EmptyReportError",
    "ReportReservePathLimitError",
    "ScheduledDownloadFailedError",
    "SoqlDownloadFailedError",
    "UnsupportedScheduleFrequencyError",
    "ScheduleWeekdayInvalidError",
    "DataLoaderError",
    "DataLoaderTimeoutError",
    "DataLoaderExecutionError",
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


# v1.0.0 以前の旧例外名は削除せず、 ``FutureWarning`` 付きの別名として残す。
# 会社側プロジェクトは ``grep`` できないため、 ``from comken.exceptions
# import OldName`` を無警告で壊すと、現場のコードがサイレントに止まる。
# 旧サブモジュール経由（``comken.exceptions.excel.ExcelFileNotFoundError`` など）は
# 対象外。パッケージ入口からの import / 属性アクセスだけをこの仕組みで救う。
_RENAMED_EXCEPTIONS: dict[str, str] = {
    "ExcelFileNotFoundError": "ComkenFileNotFoundError",
    "CSVFileNotFoundError": "ComkenFileNotFoundError",
    "AccessFileNotFoundError": "ComkenFileNotFoundError",
    "ConfigFileNotFoundError": "ComkenFileNotFoundError",
    "DataLoaderLauncherNotFoundError": "ComkenFileNotFoundError",
    "DataLoaderResultFileMissingError": "ComkenFileNotFoundError",
    "OutlookAttachmentNotFoundError": "ComkenFileNotFoundError",
    "ReportFolderNotFoundError": "ComkenFileNotFoundError",
}


def __getattr__(name: str) -> type[ComkenError]:
    """旧例外名を ``FutureWarning`` 付きの別名として公開する。"""
    new_name = _RENAMED_EXCEPTIONS.get(name)
    if new_name is None:
        raise AttributeError(f"module 'comken.exceptions' has no attribute {name!r}")
    new_cls = globals()[new_name]
    warnings.warn(
        f"{name} は {new_name} に統合されました。{new_name} に書き換えてください。",
        FutureWarning,
        stacklevel=2,
    )
    return new_cls  # type: ignore[no-any-return]
