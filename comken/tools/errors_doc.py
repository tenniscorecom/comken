"""comken/tools/errors_doc.py — エラー対応ガイド（docs/ERRORS.md）の表を例外から作り直す。

例外クラスの docstring（1 行目＝意味、「対処:」の下＝対処）と継承階層から、
非エンジニア向けのエラー名の表を組み立てる。手で書いた表は例外を足したときに
古くなるため、表の正本は docstring に置き、ここで毎回作り直す。

``docs/ERRORS.md`` は ``ERRORS_GENERATED_MARKER`` より上が手書き、下が自動生成。
手書き部分（「まず試すこと」など）は変えず、マーカーより下だけを書き換える。

**このファイルはパッケージに同梱されている（配布される）。** comken 本体の
``docs/ERRORS.md`` は開発用の ``tools/export_for_chat.py`` から、新規プロジェクトの
``docs/ERRORS.md`` は ``エラー一覧の更新.bat`` / ``python -m comken errors`` から、
どちらもここを通して作る（同じ表を 2 か所で別々に組み立てない）。
"""

import inspect
import logging
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from comken import exceptions
from comken.core.discovery import find_subclasses
from comken.core.encoding import UTF8

logger = logging.getLogger(__name__)

ERRORS_GENERATED_MARKER = "<!-- ここから下は自動生成する。手で編集しない -->"

PROJECT_ERRORS_HEADING = "プロジェクト固有のエラー（自動生成）"

# エラー対応ガイドの置き場所。プロジェクトのフォルダの下の docs/ に固定で、変えられない
# （場所を引数にすると、思わぬ場所を書き換えられるため）
ERRORS_DOC_PATH = Path("docs") / "ERRORS.md"


@dataclass(frozen=True)
class ErrorCategory:
    """エラー表1つ分の見出しと、分類に使う基底例外を持つ。"""

    heading: str
    bases: tuple[type[BaseException], ...]


ERROR_CATEGORIES = (
    ErrorCategory("Excel のエラー", (exceptions.ExcelError,)),
    ErrorCategory("Access のエラー", (exceptions.AccessError,)),
    ErrorCategory("Outlook のエラー", (exceptions.OutlookError,)),
    ErrorCategory(
        "ファイル・設定などのエラー",
        (
            exceptions.CSVError,
            exceptions.ColumnNotFoundError,
            exceptions.ConfigError,
            exceptions.StateError,
            exceptions.DownloaderError,
            exceptions.SalesforceError,
            exceptions.CredentialError,
            exceptions.HolidayError,
        ),
    ),
    ErrorCategory("ブラウザ（Edge 自動操作）のエラー", (exceptions.BrowserError,)),
    ErrorCategory("Table のエラー", (exceptions.TableError,)),
    ErrorCategory("Windows 操作のエラー", (exceptions.WindowNotFoundError,)),
)
DIRECT_ERROR_CATEGORIES = {
    exceptions.ComkenFileNotFoundError: "ファイル・設定などのエラー",
    exceptions.UnsupportedFileSuffixError: "ファイル・設定などのエラー",
    exceptions.InvalidColumnError: "ファイル・設定などのエラー",
    exceptions.SiteOwnerRequiredError: "ファイル・設定などのエラー",
    exceptions.FileDeletionError: "ファイル・設定などのエラー",
    exceptions.FileSuffixMissingError: "ファイル・設定などのエラー",
    exceptions.LoggingAlreadyConfiguredError: "ファイル・設定などのエラー",
    exceptions.LoggingConflictError: "ファイル・設定などのエラー",
    exceptions.LogRootNotConfiguredError: "ファイル・設定などのエラー",
}
SUPPLEMENTAL_ERRORS = {
    "Access のエラー": (
        (
            "PermissionError",
            "ファイルが誰かに開かれている",
            "自分や他の人がそのファイルを開いていないか確認して閉じる",
        ),
    ),
    "ファイル・設定などのエラー": (
        (
            "FileNotFoundError",
            "ファイルが見つからない",
            "ファイルの置き場所と名前を確認する。「今日の日付のファイル」を探す処理なら、"
            "今日のファイルが作られているか確認する",
        ),
    ),
    "ブラウザ（Edge 自動操作）のエラー": (
        (
            "WebDriverException",
            "ブラウザ操作の一般的なエラー",
            "Edge のウィンドウをすべて閉じて再実行する",
        ),
    ),
}
# すべてのエラーの親。カテゴリ例外（ExcelError など）はメッセージつきで直接送出するので、
# 各カテゴリの表に普通の行として載せる。
CLASSIFICATION_ERRORS = (exceptions.ComkenError,)


def update_errors_doc(project_root: Path, *, project_package: ModuleType | None = None) -> bool:
    """``project_root/docs/ERRORS.md`` の自動生成部分を作り直し、変わったら ``True`` を返す。

    置き場所は ``ERRORS_DOC_PATH``（``docs/ERRORS.md``）に固定で、変えられない。

    ``project_package`` にプロジェクトの ``src`` を渡すと、その中で定義した
    ``ComkenError`` のサブクラスの表を、comken のエラーの表の前に足す。

    マーカーが無いファイルは、手書き部分を消さないよう末尾にマーカーと表を足す。
    ファイルが無ければ作る。
    """
    path = project_root / ERRORS_DOC_PATH
    current = path.read_text(encoding=UTF8) if path.is_file() else ""
    updated = _merged_errors_text(current, project_package)
    if updated == current:
        logger.debug("エラー一覧は最新のため書き換えません: %s", path)
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated, encoding=UTF8)
    logger.debug("エラー一覧を書き換えました: %s", path)
    return True


def generated_errors_text(project_package: ModuleType | None = None) -> str:
    """マーカーより下に入れる、エラー名の表だけを返す。"""
    sections: list[str] = []
    if project_package is not None:
        project_exceptions = find_subclasses(project_package, exceptions.ComkenError)
        if project_exceptions:
            sections += [
                f"## {PROJECT_ERRORS_HEADING}",
                "",
                *_error_table(list(project_exceptions)),
                "",
            ]

    grouped: dict[str, list[type[BaseException]]] = {
        category.heading: [] for category in ERROR_CATEGORIES
    }
    for exception in _concrete_comken_exceptions():
        grouped[_error_category(exception)].append(exception)
    for category in ERROR_CATEGORIES:
        sections += [
            f"## {category.heading}",
            "",
            *_error_table(grouped[category.heading], SUPPLEMENTAL_ERRORS.get(category.heading, ())),
            "",
        ]

    sections += [
        "## すべてのエラーに共通の親",
        "",
        "`ComkenError` は、comken が出すエラーすべての親です。画面に表示されたエラー名を",
        "上の表から探してください。",
        "",
        *_error_table(list(CLASSIFICATION_ERRORS)),
    ]
    return "\n".join(sections).rstrip() + "\n"


def _merged_errors_text(current: str, project_package: ModuleType | None = None) -> str:
    """マーカーより上の手書き部分と、新しい生成部分を結合する。"""
    handwritten = current.split(ERRORS_GENERATED_MARKER, maxsplit=1)[0].rstrip()
    generated = generated_errors_text(project_package)
    if not handwritten:
        return f"{ERRORS_GENERATED_MARKER}\n\n{generated}"
    return f"{handwritten}\n\n{ERRORS_GENERATED_MARKER}\n\n{generated}"


def _concrete_comken_exceptions() -> list[type[BaseException]]:
    """``__all__`` の公開例外から、分類用の親を除いて重複なく並べる。"""
    concrete: list[type[BaseException]] = []
    for name in exceptions.__all__:
        exception = getattr(exceptions, name)
        if exception in CLASSIFICATION_ERRORS or exception in concrete:
            continue
        concrete.append(exception)
    return concrete


def _exception_details(exception: type[BaseException]) -> tuple[str, str]:
    """例外の docstring から、平易な意味と対処を取り出す。"""
    docstring = inspect.getdoc(exception)
    if not docstring:
        raise ValueError(f"{exception.__name__} に docstring がありません")
    meaning, _, remainder = docstring.partition("\n")
    treatment_marker = "\n対処:\n"
    if treatment_marker not in f"\n{remainder}":
        raise ValueError(f"{exception.__name__} の docstring に「対処:」がありません")
    treatment = remainder.split(treatment_marker.strip("\n"), maxsplit=1)[1].strip()
    if not treatment:
        raise ValueError(f"{exception.__name__} の docstring の「対処:」が空です")
    return meaning, "".join(line.strip() for line in treatment.splitlines())


def _error_category(exception: type[BaseException]) -> str:
    """継承階層から掲載カテゴリを返し、未分類なら生成を止める。"""
    direct_category = DIRECT_ERROR_CATEGORIES.get(exception)
    if direct_category:
        return direct_category
    matches = [
        category.heading
        for category in ERROR_CATEGORIES
        if any(issubclass(exception, base) for base in category.bases)
    ]
    if len(matches) != 1:
        raise ValueError(f"{exception.__name__} のカテゴリを一意に決められません: {matches}")
    return matches[0]


def _error_table(
    exceptions_in_category: list[type[BaseException]],
    supplemental_rows: tuple[tuple[str, str, str], ...] = (),
) -> list[str]:
    """例外一覧を非エンジニア向け Markdown 表にする。"""
    lines = ["| エラー名 | 意味 | 自分でできる対処 |", "|---|---|---|"]
    for exception in exceptions_in_category:
        meaning, treatment = _exception_details(exception)
        lines.append(f"| `{exception.__name__}` | {meaning} | {treatment} |")
    for name, meaning, treatment in supplemental_rows:
        lines.append(f"| `{name}` | {meaning} | {treatment} |")
    return lines
