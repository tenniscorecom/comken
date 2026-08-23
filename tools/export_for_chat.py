"""comken の公開 API ドキュメント、エラー対応ガイド、貼り付け用資料を生成する。

**このファイルは開発用**（リポジトリ直下の ``tools/`` にあり、配布されない）。
``comken/tools/`` に同梱されて ``python -m comken init`` から呼ばれる
``new_project.py`` とは役割が違うので、混同しないこと。

通常は各パッケージの ``__all__`` をたどり、型ヒント付き署名と docstring 全文を
``docs/自動生成/API.md`` へ書き出す。添付できない環境では ``--max-chars`` を指定すると、
従来どおり資料を文字数の目安で分割して ``貼り付け用/`` へ出力する。

使い方:
    python tools/export_for_chat.py
    python tools/export_for_chat.py --max-chars 20000
"""

import argparse
import ast
import inspect
import shutil
import sys
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

# スクリプトとして実行すると sys.path の先頭は tools/ になるため、
# comken を import する前にリポジトリルートを探索対象へ加える。
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

exceptions = import_module("comken.exceptions")

PACKAGE_ROOT = ROOT / "comken"
API_OUTPUT_PATH = ROOT / "docs" / "自動生成" / "API.md"
ERRORS_OUTPUT_PATH = ROOT / "docs" / "ERRORS.md"
LEGACY_OUTPUT_DIR = ROOT / "貼り付け用"
ERRORS_GENERATED_MARKER = (
    "<!-- ここから下は python export_for_chat.py が自動生成する。手で編集しない -->"
)


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
            exceptions.CsvError,
            exceptions.ColumnNotFoundError,
            exceptions.ConfigError,
            exceptions.MasterTableError,
            exceptions.MasterTableError,
            exceptions.StateError,
            exceptions.DownloaderError,
            exceptions.RpaError,
            exceptions.SalesforceError,
            exceptions.CredentialError,
            exceptions.HolidayCalendarError,
        ),
    ),
    ErrorCategory("ブラウザ（Edge 自動操作）のエラー", (exceptions.BrowserError,)),
    ErrorCategory("Table のエラー", (exceptions.TableError,)),
)
DIRECT_ERROR_CATEGORIES = {
    exceptions.UnsupportedFileSuffixError: "ファイル・設定などのエラー",
    exceptions.InvalidColumnError: "ファイル・設定などのエラー",
    exceptions.SiteOwnerRequiredError: "ファイル・設定などのエラー",
    exceptions.FileDeletionError: "ファイル・設定などのエラー",
    exceptions.TransferDestinationRowMissingError: "ファイル・設定などのエラー",
    exceptions.TransferDestinationMultipleMatchError: "ファイル・設定などのエラー",
    exceptions.LoggingAlreadyConfiguredError: "ファイル・設定などのエラー",
    exceptions.LoggerHostNotConfiguredError: "ファイル・設定などのエラー",
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
CLASSIFICATION_ERRORS = (
    exceptions.ComkenError,
    exceptions.ExcelError,
    exceptions.AccessError,
    exceptions.CsvError,
    exceptions.ColumnNotFoundError,
    exceptions.ConfigError,
    exceptions.StateError,
    exceptions.DownloaderError,
    exceptions.RpaError,
    exceptions.SalesforceError,
    exceptions.CredentialError,
    exceptions.BrowserError,
    exceptions.TableError,
)

BUNDLES: dict[str, tuple[str, list[str]]] = {
    "1_コーディング規約": (
        "これは社内 Python ライブラリ comken を使うツールの**コーディング規約**です。"
        "以後このスレッドで書くコードは、この規約に従ってください。",
        ["CONVENTIONS.md"],
    ),
    "2_ライブラリの使い方": (
        "これは社内 Python ライブラリ comken の**API 一覧**です。"
        "comken を使うコードを書くときは、ここに載っている関数・引数だけを使ってください。"
        "載っていない機能は「comken には無い」と判断し、勝手に作らず標準ライブラリで書くか、"
        "その旨を伝えてください。",
        ["README.md", "@API"],
    ),
    "3_ドキュメントの書き方": (
        "これは社内ツールに付ける**仕様書とエラー対応ガイドのひな形**です。"
        "新しいツールのドキュメントを書くときは、この構成と書き方に合わせてください。",
        [
            "templates/新規プロジェクト/docs/仕様書.md",
            "templates/新規プロジェクト/docs/使い方.md",
            "ERRORS.md",
        ],
    ),
    "4_ライブラリ自体を直す人向け": (
        "これは社内ライブラリ comken **本体**を修正するときの規約です。"
        "comken を使うだけなら不要です。",
        ["docs/開発/ライブラリ開発規約.md"],
    ),
}


def _parse(path: Path) -> ast.Module:
    """UTF-8 の Python ファイルを AST として読む。"""
    return ast.parse(path.read_text(encoding="utf-8"))


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """関数定義から本文を除き、型ヒントを含む署名を返す。"""
    stub = type(node)(
        name=node.name,
        args=node.args,
        body=[ast.Expr(value=ast.Constant(value=...))],
        decorator_list=node.decorator_list,
        returns=node.returns,
        type_params=getattr(node, "type_params", []),
    )
    ast.fix_missing_locations(stub)
    return ast.unparse(stub).replace("\n    ...", "").rstrip()


def _all_names(tree: ast.Module) -> list[str]:
    """``__all__`` の文字列要素を定義順に返す。"""
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
        if "__all__" in targets and isinstance(node.value, (ast.List, ast.Tuple)):
            return [
                element.value
                for element in node.value.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            ]
    return []


def _source_for_import(package_file: Path, node: ast.ImportFrom) -> Path | None:
    """import の参照先 Python ファイルを返す（絶対 import / 相対 import 両方）。"""
    if not node.module:
        return None
    if node.level == 0:
        # 絶対 import。PACKAGE_ROOT からの相対として解決する
        if node.module == "comken":
            source = PACKAGE_ROOT
        elif node.module.startswith("comken."):
            source = PACKAGE_ROOT.joinpath(*node.module[len("comken.") :].split("."))
        else:
            # comken 配下以外の import はこのツールでは追わない
            return None
    else:
        # 相対 import。package_file から level-1 階層上を起点に解決する
        base = package_file.parent
        for _ in range(node.level - 1):
            base = base.parent
        source = base.joinpath(*node.module.split("."))
    module_path = source.with_suffix(".py")
    package_path = source / "__init__.py"
    if module_path.exists():
        return module_path
    if package_path.exists():
        return package_path
    return None


def _find_definition(path: Path, name: str) -> tuple[Path, ast.AST] | None:
    """再エクスポートをたどり、名前の定義元と AST ノードを返す。"""
    tree = _parse(path)
    for node in tree.body:
        if (
            isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ):
            return path, node
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == name for target in targets):
                return path, node
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        source = _source_for_import(path, node)
        if source is None:
            continue
        for alias in node.names:
            if (alias.asname or alias.name) == name:
                return _find_definition(source, alias.name)
    return None


def _doc_lines(
    node: ast.AsyncFunctionDef | ast.FunctionDef | ast.ClassDef | ast.Module,
    heading_level: int,
) -> list[str]:
    """docstring 全文を Markdown の節として返す。"""
    docstring = ast.get_docstring(node, clean=True)
    if not docstring:
        return []
    return [f"{'#' * heading_level} 説明", "", docstring, ""]


def _class_lines(node: ast.ClassDef) -> list[str]:
    """公開クラスの宣言、docstring、公開メソッドを Markdown にする。"""
    bases = ", ".join(ast.unparse(base) for base in node.bases)
    declaration = f"class {node.name}({bases}):" if bases else f"class {node.name}:"
    lines = ["```text", declaration, "```", "", *_doc_lines(node, 4)]
    for child in node.body:
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if child.name.startswith("_") and child.name != "__init__":
            continue
        lines += [f"#### `{child.name}`", "", "```text", _signature(child), "```", ""]
        lines += _doc_lines(child, 5)
    return lines


def _definition_lines(name: str, node: ast.AST) -> list[str]:
    """公開名1つ分の Markdown を返す。"""
    lines = [f"### `{name}`", ""]
    if isinstance(node, ast.ClassDef):
        return [*lines, *_class_lines(node)]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return [*lines, "```text", _signature(node), "```", "", *_doc_lines(node, 4)]
    return [*lines, "公開定数。", ""]


def _api_text() -> str:
    """``__all__`` ベースの公開 API リファレンスを組み立てる。"""
    sections = [
        "# comken 公開 API",
        "",
        "> [!IMPORTANT]",
        "> このファイルは自動生成物です。手で編集しないでください。",
        "> 再生成: `python export_for_chat.py`",
        "",
        "[README（ドキュメントの入口）へ戻る](../../README.md)",
        "",
        "各パッケージの `__all__` にある公開名だけを掲載しています。",
    ]
    modules = [path for path in PACKAGE_ROOT.glob("*.py") if path.name != "__init__.py"]
    sources = sorted(PACKAGE_ROOT.rglob("__init__.py")) + sorted(modules)
    for source in sources:
        names = _all_names(_parse(source))
        if not names:
            continue
        module = source.parent if source.name == "__init__.py" else source.with_suffix("")
        module_path = ".".join(module.relative_to(ROOT).parts)
        sections += ["", f"## `from {module_path} import ...`", ""]
        for name in names:
            definition = _find_definition(source, name)
            if definition is None:
                sections += [f"### `{name}`", "", "定義を解決できませんでした。", ""]
                continue
            _, node = definition
            sections += _definition_lines(name, node)
    return "\n".join(sections).rstrip() + "\n"


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


def _errors_generated_text() -> str:
    """公開例外の docstring と継承階層からエラー一覧を組み立てる。"""
    public_exceptions = [getattr(exceptions, name) for name in exceptions.__all__]
    concrete_exceptions = [
        exception for exception in public_exceptions if exception not in CLASSIFICATION_ERRORS
    ]
    grouped: dict[str, list[type[BaseException]]] = {
        category.heading: [] for category in ERROR_CATEGORIES
    }
    for exception in concrete_exceptions:
        grouped[_error_category(exception)].append(exception)

    sections: list[str] = []
    for category in ERROR_CATEGORIES:
        sections += [
            f"## {category.heading}",
            "",
            *_error_table(grouped[category.heading], SUPPLEMENTAL_ERRORS.get(category.heading, ())),
            "",
        ]

    sections += [
        "## 分類（まとめて捕捉する用）",
        "",
        "次の名前は、似たエラーをプログラム側でまとめて扱うための分類です。",
        "これらの名前が単独で表示されることはありません。対処するときは、画面に表示された",
        "具体的なエラー名を上の表から探してください。",
        "",
        *_error_table(list(CLASSIFICATION_ERRORS)),
    ]
    return "\n".join(sections).rstrip() + "\n"


def _merged_errors_text(current: str) -> str:
    """マーカーより上の手書き部分と、新しい生成部分を結合する。

    マーカーが見つからない場合は、手書き部分を誤って消さないため ValueError にする。
    """
    if ERRORS_GENERATED_MARKER not in current:
        raise ValueError(
            f"{ERRORS_OUTPUT_PATH.name} に自動生成マーカーがありません。"
            "手書き部分は変更していません"
        )
    handwritten = current.split(ERRORS_GENERATED_MARKER, maxsplit=1)[0].rstrip()
    generated = _errors_generated_text()
    return f"{handwritten}\n\n{ERRORS_GENERATED_MARKER}\n\n{generated}"


def _write_errors() -> None:
    """ERRORS.md の手書き部分を残して、生成部分だけを書き換える。"""
    current = ERRORS_OUTPUT_PATH.read_text(encoding="utf-8")
    ERRORS_OUTPUT_PATH.write_text(_merged_errors_text(current), encoding="utf-8")


def _bundle_text(title: str, purpose: str, sources: list[str]) -> str:
    """貼り付け用資料1種類のテキストを組み立てる。"""
    parts = [f"# {title}", "", purpose, ""]
    for source in sources:
        if source == "@API":
            parts += ["", "=" * 60, "", _api_text()]
            continue
        parts += ["", "=" * 60, f"（資料: {source}）", "=" * 60, ""]
        parts.append((ROOT / source).read_text(encoding="utf-8-sig").rstrip())
    return "\n".join(parts) + "\n"


def _split(text: str, max_chars: int) -> list[str]:
    """行の途中で切らず、指定文字数を目安に分割する。"""
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.splitlines(keepends=True):
        if current and size + len(line) > max_chars:
            chunks.append("".join(current))
            current = []
            size = 0
        current.append(line)
        size += len(line)
    if current:
        chunks.append("".join(current))
    return chunks


def _write_legacy_bundles(max_chars: int) -> None:
    """従来の貼り付け用分割テキストを生成する。"""
    if max_chars <= 0:
        raise ValueError("--max-chars には1以上の整数を指定してください")
    if LEGACY_OUTPUT_DIR.exists():
        shutil.rmtree(LEGACY_OUTPUT_DIR)
    LEGACY_OUTPUT_DIR.mkdir()
    for title, (purpose, sources) in BUNDLES.items():
        chunks = _split(_bundle_text(title, purpose, sources), max_chars)
        for number, chunk in enumerate(chunks, start=1):
            suffix = "" if len(chunks) == 1 else f"_{number}of{len(chunks)}"
            path = LEGACY_OUTPUT_DIR / f"{title}{suffix}.txt"
            header = "" if number == 1 else f"（{title} の続き {number}/{len(chunks)}）\n\n"
            path.write_text(header + chunk, encoding="utf-8")
            print(f"{path.name}  {len(chunk):,} 文字")  # noqa: T201


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-chars",
        type=int,
        help="指定時だけ、貼り付け用資料をこの文字数の目安で分割して出力する",
    )
    args = parser.parse_args()
    API_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    API_OUTPUT_PATH.write_text(_api_text(), encoding="utf-8")
    print(f"{API_OUTPUT_PATH.relative_to(ROOT)} を生成しました")  # noqa: T201
    _write_errors()
    print(f"{ERRORS_OUTPUT_PATH.relative_to(ROOT)} を生成しました")  # noqa: T201
    if args.max_chars is not None:
        _write_legacy_bundles(args.max_chars)


if __name__ == "__main__":
    main()
