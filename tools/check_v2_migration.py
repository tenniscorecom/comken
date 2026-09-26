"""v2.0.0 への移行チェック用スクリプト（社内 PC で動かす開発・運用ツール）。

会社の PC で、**社内プロジェクトのフォルダ**を指定して実行し、
**v2.0.0 で使えなくなった comken の名前を使っている行**を一覧にする。

    python tools/check_v2_migration.py <調べるフォルダ> [<フォルダ> ...]

標準ライブラリだけで動く（comken への依存は無く、``import comken`` も不要）。
ただし、公認サイトの ``NAME`` 一覧だけは ``comken.toolbox.browser.sites.SITES``
を import できたらそこから作り、できなかったら埋め込みの一覧を使う。

対象は再帰的に ``*.py`` を走査する。``.git`` / ``__pycache__`` / ``.venv`` /
``venv`` / ``typings`` / ``comken`` という名前のフォルダは飛ばす。

検出する種類:

1. **消えたモジュール**（埋め込み一覧の 30 個）: ``import X`` / ``from X import`` で
   X がその名前か、その配下にあるものを検出
2. **消えた公開名**（埋め込み一覧の 90 個）: 単語として出現（``\\b名前\\b``）。
   コメント行も検出対象に含める（コメントで古い名前を説明していることもあるため）
3. **Sheet から削除したメソッド**（13 個）: ``.名前(`` の形。openpyxl の worksheet
   にも ``merge_cells`` / ``unmerge_cells`` があるため、この2つだけは種類を
   「要確認」にする
4. **DateFileFinder の削除メソッド**: ``.dated(`` 全部と、同じ行に ``DateFileFinder``
   を含む ``.prefix(`` だけ。``DateNameBuilder(...).prefix()`` は今も有効なので、
   ``DateFileFinder`` を含まない行の ``.prefix(`` は出さない
5. **ブラウザ公認サイトと同じ ``NAME``**: ``NAME = "..."``（``'...'`` も）で、
   値が公認サイトの ``NAME``（``ams`` / ``ntt_east`` / ``ntt_west`` / ``ouju`` /
   ``salesforce_solution`` / ``salesforce_solution_sandbox``）と一致するもの。
   v2.0.0 から、プロジェクト側で同じ ``NAME`` のサイトクラスを作ると起動時に
   ``BrowserError`` になる

出力: ``パス:行番号: [種類] 名前: 行の内容（前後の空白を除く、120文字まで）``。
最後に件数の合計。**1件でもあれば終了コード 1、無ければ 0**。何も見つからなければ
「見つかりませんでした」と出す。

誤検出について:

- 種類 3（Sheet メソッド）と 種類 4（DateFileFinder）は、``.prefix(`` /
  ``.merge_cells(`` などのメソッド呼び出しの構えだけを機械的に拾うため、
  openpyxl の worksheet や ``DateNameBuilder`` のような別クラスの同名メソッドを
  拾ってしまうことがある（種類 3 の merge_cells / unmerge_cells は必ず「要確認」
  として出す）。出力された行が本当に「v2.0.0 で壊れる箇所」かどうかは、
  新しい名前は comken の docs（機能ごとのドキュメント・``docs/自動生成/API.md``）
  で確認すること。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# スクリプトとして実行すると sys.path の先頭は tools/ になるため、
# comken を import する前にリポジトリルートを探索対象へ加える。
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 消えたモジュール（30）。タグ v1.1.1 と HEAD の ``__init__.py`` の ``__all__`` を
# 比較して機械的に出した一覧。
REMOVED_MODULES: tuple[str, ...] = (
    "comken.constants",
    "comken.core.calendar",
    "comken.core.calendar._calendar",
    "comken.core.clock",
    "comken.core.data",
    "comken.exceptions.access",
    "comken.exceptions.browser",
    "comken.exceptions.calendar",
    "comken.exceptions.column",
    "comken.exceptions.credential",
    "comken.exceptions.csv",
    "comken.exceptions.dataloader",
    "comken.exceptions.excel",
    "comken.exceptions.file",
    "comken.exceptions.logger",
    "comken.exceptions.master_table",
    "comken.exceptions.outlook",
    "comken.exceptions.salesforce",
    "comken.exceptions.state",
    "comken.exceptions.table",
    "comken.exceptions.warning",
    "comken.exceptions.windows",
    "comken.services.salesforce_downloader.soql_reports.new_report",
    "comken.toolbox.browser.management.browsers",
    "comken.toolbox.browser.management.tasks",
    "comken.toolbox.browser.sites.salesforce.registry",
    "comken.toolbox.salesforce._bulk_paging",
    "comken.toolbox.salesforce.bulk_ingest",
    "comken.toolbox.salesforce.bulk_query",
    "comken.toolbox.salesforce.dataloader",
)

# 消えた公開名（90）。タグ v1.1.1 と HEAD の各 ``__init__.py`` の ``__all__`` を
# 比較して機械的に出した一覧。openpyxl の ``merge_cells`` 等は含めない（モジュール
# として comken に無いため、ここには載せていない）。
REMOVED_PUBLIC_NAMES: tuple[str, ...] = (
    "AccessBackupError",
    "AccessLocalCopyError",
    "AccessRoutineError",
    "AccessSourceNotFoundError",
    "BUSINESS_DAY_SEARCH_LIMIT",
    "BackgroundTask",
    "BrowserClosedError",
    "BrowserNotStartedError",
    "Browsers",
    "BulkIngestResult",
    "BusinessDayNotFoundError",
    "CALENDAR_CSV_PATH",
    "CSVHeaderError",
    "CSVRowLengthError",
    "CalendarError",
    "CalendarFormatError",
    "ClassicOutlookNotAvailableError",
    "ConcurrentSessionUseError",
    "ConfigCreatedFromExampleError",
    "ConfigLowerCaseNameError",
    "ConfigMappingEmptyValueError",
    "ConfigSectionNotFoundError",
    "ConfigSubclassingNotSupportedError",
    "CredentialDecryptionError",
    "CredentialImportError",
    "CredentialStoreCorruptedError",
    "DataLoaderCLI",
    "DataLoaderError",
    "DataLoaderExecutionError",
    "DataLoaderResult",
    "DataLoaderTimeoutError",
    "DownloadTimeoutError",
    "DriverStartError",
    "EncodingDetectionError",
    "ExcelHeaderError",
    "ExcelNameError",
    "ExcelSaveError",
    "ExcelUsageError",
    "InvalidCredentialNameError",
    "InvalidTableOperationError",
    "KeyColumnNotFoundError",
    "MacroError",
    "MasterColumnNotFoundError",
    "MasterSheetNotDefinedError",
    "OutlookFolderNotFoundError",
    "PopupTabNotOpenedError",
    "ReportDisabledError",
    "SOQL_REPORTS",
    "SalesforceBulkFailedError",
    "SalesforceBulkTimeoutError",
    "SalesforceConnectionError",
    "SalesforceCredentialRotationError",
    "SalesforceExternalIDMissingError",
    "SalesforceReportAccessDeniedError",
    "SalesforceReportExecutionError",
    "SalesforceReportExportError",
    "SalesforceReportFormatError",
    "SalesforceSiteBase",
    "SalesforceSiteNotFoundError",
    "SalesforceSiteSelectionError",
    "ScheduleSettingError",
    "SessionNameConflictError",
    "SessionNotFoundError",
    "SiteAlreadyInLibraryError",
    "SiteConfigError",
    "SolutionSandboxSite",
    "SolutionSite",
    "SoqlDownloadFailedError",
    "StateFileCorruptedError",
    "StateLowerCaseNameError",
    "StateValueTypeError",
    "TableColumnMismatchError",
    "TableFormulaOverwriteError",
    "TableNotFoundError",
    "TableNotOpenError",
    "TableRowColumnsError",
    "TableTypeConversionError",
    "TransferDestinationMissingError",
    "TransferDestinationMultipleMatchError",
    "add_business_days",
    "business_day_after",
    "business_day_before",
    "business_day_on_or_after",
    "business_day_on_or_before",
    "copy_to_local_if_large",
    "first_business_day_of_month",
    "is_business_day",
    "last_business_day_of_month",
    "nth_business_day_of_month",
    "warn_if_calendar_expiring_soon",
)

# Sheet から削除したメソッド。openpyxl の worksheet にも ``merge_cells`` /
# ``unmerge_cells`` があるため、誤検出を避ける目的で「要確認」と表示する。
SHEET_REMOVED_METHODS: tuple[str, ...] = (
    "set_border",
    "merge_cells",
    "unmerge_cells",
    "set_row_height",
    "set_column_width",
    "hide_row",
    "show_row",
    "hide_column",
    "show_column",
    "insert_row",
    "delete_row",
    "insert_column",
    "delete_column",
)

# openpyxl の worksheet にも同名があるため種類を「要確認」にするメソッド名。
# （種類 3 の検出は ``.merge_cells(`` などの形を機械的に拾うため、openpyxl の
# worksheet を操作するコードを誤検出する。これを「要確認」として利用者に伝える）
_NEEDS_REVIEW_METHODS = frozenset({"merge_cells", "unmerge_cells"})

# 走査で除外するフォルダ名（どの階層でも）。
EXCLUDED_DIR_NAMES = frozenset(
    {
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "typings",
        "comken",
    }
)

# import 文の正規表現。``import X`` / ``import X as Y`` / ``from X import ...`` を拾う。
# 空白の多寡・相対 import には対応しない（comken は絶対 import のみを使うため不要）。
_IMPORT_RE = re.compile(
    r"^\s*(?:"
    r"from\s+([\w.]+)\s+import|"
    r"import\s+([\w.]+)"
    r")\s*(?:as\s+\w+)?"
)

# 単語境界付きの検出（``\b``）。``fooBar`` 等に含まれる ``Bar`` は拾わない。
# 公開名は英字・数字・アンダースコアのみのため \w で十分。
_WORD_RE_TEMPLATE = r"\b{name}\b"

# Sheet メソッドの呼び出し形（``.merge_cells(`` 等）。
_METHOD_CALL_RE_TEMPLATE = r"\.{name}\s*\("

# ``NAME = "..."`` / ``NAME = '...'`` の代入（種類 5）。
_NAME_ASSIGN_RE = re.compile(r"""^\s*NAME\s*=\s*(?P<quote>['"])(?P<value>[^'"]+)(?P=quote)\s*$""")


def _detect_browser_site_names() -> set[str]:
    """公認サイトの ``NAME`` 一覧を返す。

    ``comken.toolbox.browser.sites.SITES`` から動的に集めるのが望ましいが、
    このツールは comken 無しでも動く必要がある。import に失敗したら
    埋め込み一覧にフォールバックする。埋め込み一覧はタグ ``v1.1.1`` 時点の
    公認サイトを反映している（``ams`` / ``ouju`` の削除は別作業）。
    """
    embedded = {
        "ams",
        "ntt_east",
        "ntt_west",
        "ouju",
        "salesforce_solution",
        "salesforce_solution_sandbox",
    }
    try:
        from comken.toolbox.browser.sites import SITES

        return {cls.NAME for cls in SITES if cls.NAME} | embedded
    except Exception:
        # comken が import できなくても致命ではない（埋め込みで動かす）
        return embedded


def _iter_python_files(folders: list[Path]) -> list[Path]:
    """指定フォルダ配下の ``*.py`` を再帰的に集める（除外フォルダは飛ばす）。"""
    results: list[Path] = []
    for folder in folders:
        if not folder.exists() or not folder.is_dir():
            print(f"警告: フォルダが存在しません: {folder}", file=sys.stderr)
            continue
        for path in folder.rglob("*.py"):
            if not path.is_file():
                continue
            parts = path.relative_to(folder).parts
            if any(part in EXCLUDED_DIR_NAMES for part in parts):
                continue
            results.append(path)
    return sorted(results)


def _check_removed_modules(line: str) -> list[tuple[str, str]]:
    """import 行から消えたモジュールを検出し、[(名前, 種類)] の組を返す。"""
    match = _IMPORT_RE.match(line)
    if match is None:
        return []
    imported = match.group(1) or match.group(2) or ""
    hits: list[tuple[str, str]] = []
    for module in REMOVED_MODULES:
        # ``comken.core.calendar`` を import しているなら
        # ``comken.core.calendar`` 自体も ``comken.core.calendar._calendar`` も
        # ヒットする（モジュール名の先頭一致）。
        if imported == module or imported.startswith(module + "."):
            hits.append((module, "消えたモジュール"))
    return hits


def _check_removed_public_names(line: str) -> list[tuple[str, str]]:
    """行内から消えた公開名を単語境界付きで検出する。"""
    hits: list[tuple[str, str]] = []
    for name in REMOVED_PUBLIC_NAMES:
        pattern = _WORD_RE_TEMPLATE.format(name=re.escape(name))
        if re.search(pattern, line):
            hits.append((name, "消えた公開名"))
    return hits


def _check_sheet_methods(line: str) -> list[tuple[str, str]]:
    """Sheet から削除したメソッド呼び出しを ``.メソッド(`` の形で検出する。"""
    hits: list[tuple[str, str]] = []
    for method in SHEET_REMOVED_METHODS:
        pattern = _METHOD_CALL_RE_TEMPLATE.format(name=re.escape(method))
        if re.search(pattern, line):
            category = (
                "Sheet削除メソッド(要確認)"
                if method in _NEEDS_REVIEW_METHODS
                else "Sheet削除メソッド"
            )
            hits.append((method, category))
    return hits


def _check_date_file_finder_methods(line: str) -> list[tuple[str, str]]:
    """``DateFileFinder`` の削除メソッドを検出する。

    - ``.dated(`` は全部（``DateFileFinder(...).dated(...)`` が必ずこの形になるため）
    - ``.prefix(`` は **同じ行に** ``DateFileFinder`` を含む行だけ
      （``DateNameBuilder(...).prefix()`` は今も有効なので誤検出を避ける）
    """
    hits: list[tuple[str, str]] = []
    if re.search(r"\.dated\s*\(", line):
        hits.append(("dated", "DateFileFinder削除メソッド"))
    if re.search(r"\.prefix\s*\(", line) and "DateFileFinder" in line:
        hits.append(("prefix", "DateFileFinder削除メソッド"))
    return hits


def _check_browser_site_name(line: str, official_names: set[str]) -> list[tuple[str, str]]:
    """``NAME = "..."`` の値が公認サイトの ``NAME`` と一致するかを検出する。"""
    match = _NAME_ASSIGN_RE.match(line)
    if match is None:
        return []
    value = match.group("value")
    if value in official_names:
        return [(value, "公認サイトNAME衝突")]
    return []


def _scan_file(path: Path, official_names: set[str]) -> list[tuple[int, str, str, str]]:
    """1ファイルを走査して ``(行番号, 種類, 名前, 行内容)`` のリストを返す。"""
    findings: list[tuple[int, str, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # バイナリ・読み込み不能はスキップ（社内プロジェクトの .py は大抵 UTF-8）
        return findings
    for index, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        detectors = (
            _check_removed_modules,
            _check_removed_public_names,
            _check_sheet_methods,
            _check_date_file_finder_methods,
            lambda content: _check_browser_site_name(content, official_names),
        )
        for detector in detectors:
            for name, category in detector(line):
                findings.append((index, category, name, line[:120]))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="v2.0.0 で消えた comken の名前をチェックする")
    parser.add_argument(
        "folders",
        nargs="+",
        type=Path,
        help="走査対象のフォルダ（複数指定可）",
    )
    args = parser.parse_args()

    official_names = _detect_browser_site_names()
    files = _iter_python_files(args.folders)
    total_findings = 0
    for path in files:
        findings = _scan_file(path, official_names)
        for line_number, category, name, content in findings:
            print(f"{path}:{line_number}: [{category}] {name}: {content}")
            total_findings += 1
    if total_findings == 0:
        print("見つかりませんでした")
        return 0
    print(f"合計 {total_findings} 件")
    return 1


if __name__ == "__main__":
    sys.exit(main())
