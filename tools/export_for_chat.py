"""comken の公開 API ドキュメント、エラー対応ガイド、チャット貼り付け用資料を生成する。

**このファイルは開発用**（リポジトリ直下の ``tools/`` にあり、配布されない）。
``comken/tools/`` に同梱されて ``python -m comken init`` から呼ばれる
``new_project.py`` とは役割が違うので、混同しないこと。

各パッケージの ``__all__`` をたどり、型ヒント付き署名と docstring 全文を
``docs/自動生成/API.md`` へ書き出す。

**同時に、社内の外部 AI へ貼るための資料（``comken_bundle/``）も既定で生成する。**
章ごと（規約 → API 索引 → 実例 → 実装全文 → エラー対応表 → 設計判断 → 新規プロジェクトの
テンプレ → ライブラリ開発規約）にファイルを分け、実装全文はさらに ``comken/`` 直下の
パッケージ単位（core・toolbox・services 等）で分ける。1ファイルにまとめると数百万文字に
なり、チャットへ貼るには長すぎるため。1章が ``--max-chars``（既定40万字）を超える
場合のみ、さらに複数ファイルへ割る。

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
BUNDLE_OUTPUT_DIR = ROOT / "comken_bundle"

# 1章（_bundle_sections() の1項目）がこれを超えたときだけ、さらに複数ファイルへ割る。
# 基本は「1章 = 1ファイル」を保ちたいので、普段は超えない大きめの値にする。
DEFAULT_MAX_CHARS = 400_000
ERRORS_GENERATED_MARKER = (
    "<!-- ここから下は python export_for_chat.py が自動生成する。手で編集しない -->"
)

# comken/ 配下の .py を連結するときに除外するディレクトリ名。**どの階層でも除外**。
# rglob のフィルタで弾く。 concat_source.py から引き継いだ除外に加え、
# ビルド系（build/, dist/, *.egg-info/, .venv/）も追加している。
EXCLUDED_DIR_NAMES = frozenset(
    {
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "build",
        "dist",
        ".venv",
        "venv",
    }
)

# .py 連結時に「ディレクトリ名 + .egg-info で終わるもの」を除外する接尾辞
_EXCLUDED_DIR_SUFFIXES = (".egg-info",)


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
            exceptions.MasterTableError,
            exceptions.StateError,
            exceptions.DownloaderError,
            exceptions.SalesforceError,
            exceptions.CredentialError,
            exceptions.HolidayCalendarError,
        ),
    ),
    ErrorCategory("ブラウザ（Edge 自動操作）のエラー", (exceptions.BrowserError,)),
    ErrorCategory("Table のエラー", (exceptions.TableError,)),
    ErrorCategory("Windows 操作のエラー", (exceptions.WindowNotFoundError,)),
    ErrorCategory("Data Loader のエラー", (exceptions.DataLoaderError,)),
)
DIRECT_ERROR_CATEGORIES = {
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
CLASSIFICATION_ERRORS = (
    exceptions.ComkenError,
    exceptions.ExcelError,
    exceptions.AccessError,
    exceptions.CSVError,
    exceptions.ColumnNotFoundError,
    exceptions.ConfigError,
    exceptions.StateError,
    exceptions.DownloaderError,
    exceptions.SalesforceError,
    exceptions.CredentialError,
    exceptions.BrowserError,
    exceptions.TableError,
)


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


def _own_methods(node: ast.ClassDef) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """クラス自身の本体にある公開メソッド（__init__ は含む）。"""
    return [
        child
        for child in node.body
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
        and (not child.name.startswith("_") or child.name == "__init__")
    ]


def _collect_methods_from_bases(
    node: ast.ClassDef, path: Path, seen: set[str]
) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """同一パッケージ内で解決できる基底クラスから、公開メソッドを再帰的に集める。

    Mixin合成だけで出来ていて自身に公開メソッドを持たないクラス（例: Page）を
    ドキュメント化するときに使う。外部ライブラリの基底クラス（NamedTuple など）は
    _find_definition が解決できないので黙ってスキップする。
    """
    collected: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for base in node.bases:
        if not isinstance(base, ast.Name):
            continue
        resolved = _find_definition(path, base.id)
        if resolved is None:
            continue
        base_path, base_node = resolved
        if not isinstance(base_node, ast.ClassDef):
            continue
        for method in _own_methods(base_node):
            if method.name not in seen:
                seen.add(method.name)
                collected.append(method)
        collected += _collect_methods_from_bases(base_node, base_path, seen)
    return collected


def _class_lines(node: ast.ClassDef, path: Path) -> list[str]:
    """公開クラスの宣言、docstring、公開メソッドを Markdown にする。"""
    bases = ", ".join(ast.unparse(base) for base in node.bases)
    declaration = f"class {node.name}({bases}):" if bases else f"class {node.name}:"
    lines = ["```text", declaration, "```", "", *_doc_lines(node, 4)]
    methods = _own_methods(node)
    if not methods:
        methods = _collect_methods_from_bases(node, path, set())
    for child in methods:
        lines += [f"#### `{child.name}`", "", "```text", _signature(child), "```", ""]
        lines += _doc_lines(child, 5)
    return lines


def _definition_lines(name: str, node: ast.AST, path: Path) -> list[str]:
    """公開名1つ分の Markdown を返す。"""
    lines = [f"### `{name}`", ""]
    if isinstance(node, ast.ClassDef):
        return [*lines, *_class_lines(node, path)]
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
            path, node = definition
            sections += _definition_lines(name, node, path)
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
    concrete_exceptions = []
    for exception in public_exceptions:
        if exception in CLASSIFICATION_ERRORS:
            continue
        if exception in concrete_exceptions:
            continue
        concrete_exceptions.append(exception)
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


def _collect_python_files(package_root: Path) -> list[Path]:
    """``comken/`` 配下の .py を lexical ソートして返す。

    除外ディレクトリ以外の全階層で ``.py`` だけを拾う。``.pyc`` は拡張子で除外される。
    ``build/`` / ``dist/`` / ``*.egg-info/`` / ``.venv/`` 等のビルド系ディレクトリは
    rglob のフィルタで除外する。``concat_source.py`` からロジックを引き継ぎ、
    ビルド系の除外を追加した。
    """
    if not package_root.is_dir():
        raise FileNotFoundError(f"走査対象が見つかりません: {package_root}")
    files: list[Path] = []
    for path in sorted(package_root.rglob("*.py")):
        parts = path.relative_to(package_root).parts
        if any(part in EXCLUDED_DIR_NAMES for part in parts):
            continue
        if any(part.endswith(_EXCLUDED_DIR_SUFFIXES) for part in parts):
            continue
        if not path.is_file():
            continue
        files.append(path)
    return files


def _concatenate_files(files: list[Path], package_root: Path) -> tuple[str, int, int]:
    """各ファイルの前に区切りヘッダを差し込み、結合テキストと統計を返す。

    戻り値は (テキスト, 総行数, 総バイト数) 。行数は ``splitlines()`` ベースで数える。
    ファイル末尾には必ず改行を 1 つ足してから結合する（連結が崩れないように）。
    """
    chunks: list[str] = []
    total_bytes = 0
    for path in files:
        relative = path.relative_to(package_root.parent)  # comken/ からの相対パス
        header = f"# ===== FILE: {relative.as_posix()} =====\n"
        body = path.read_text(encoding="utf-8")
        if not body.endswith("\n"):
            body += "\n"
        chunks.append(header)
        chunks.append(body)
        total_bytes += len(header.encode("utf-8")) + len(body.encode("utf-8"))
    text = "".join(chunks)
    line_count = len(text.splitlines())
    return text, line_count, total_bytes


def _bundle_sections() -> list[tuple[str, str]]:
    """社外 AI へ貼るための資料を、章（カテゴリ）ごとの (タイトル, 本文) の並びで組み立てる。

    章は少数の大きなまとまりにしている（細かく分けすぎると、逆にどれを渡せば
    いいか分かりにくくなるため）。1章が ``--max-chars``（既定40万字）を超える
    ときだけ、書き出し側の ``_split()`` で機械的に複数ファイルへ割る
    （章の中身で分け方を変えたりはしない）。

    並び順は **ヘッダ → 規約・API索引・実例 → 実装全文 → エラー対応表・設計判断
    → 新規プロジェクト向け**。規約を先頭に置くのは、社外 AI に規約（命名・
    型ヒント・定数・例外・ロギング）を最初に読ませて、生成コードの表記ブレや
    規約違反を防ぐため。最後の「新規プロジェクト向け」は使う人を選ぶ資料
    （新しいツールを作る人・comken 本体を直す人）なので最後に置く。

    章ごとに別ファイルへ書き出す前提のため、1ファイルへ結合したときに使う
    区切り線（``---``）はここでは入れない。
    """
    conventions_path = ROOT / "docs" / "開発" / "CONVENTIONS.md"
    spec_path = ROOT / "docs" / "開発" / "仕様書.md"
    conventions_text = conventions_path.read_text(encoding="utf-8").rstrip()
    spec_text = spec_path.read_text(encoding="utf-8").rstrip()

    api_text = _api_text()
    errors_text = _errors_generated_text()
    package_files = _collect_python_files(PACKAGE_ROOT)
    impl_text, impl_line_count, impl_byte_count = _concatenate_files(package_files, PACKAGE_ROOT)

    # 動く実例: examples/ 配下をすべて .py / README.md の順で並べる。
    examples_root = ROOT / "examples"
    examples_chunks: list[str] = []
    examples_files: list[Path] = []
    if examples_root.is_dir():
        # .py と README.md のみを集める。README.md は先頭に置く。
        readmes = sorted(examples_root.rglob("README.md"))
        py_files = sorted(path for path in examples_root.rglob("*.py") if path.is_file())
        for path in readmes + py_files:
            relative = path.relative_to(ROOT)
            examples_chunks.append(f"# ===== EXAMPLE: {relative.as_posix()} =====\n")
            examples_chunks.append(path.read_text(encoding="utf-8"))
            if not examples_chunks[-1].endswith("\n"):
                examples_chunks[-1] += "\n"
            examples_files.append(path)

    new_project_docs_dir = PACKAGE_ROOT / "templates" / "新規プロジェクト" / "docs"
    new_project_text = "\n\n---\n\n".join(
        f"# ===== FILE: {path.relative_to(ROOT).as_posix()} =====\n\n"
        + path.read_text(encoding="utf-8").rstrip()
        for path in (new_project_docs_dir / "仕様書.md", new_project_docs_dir / "使い方.md")
    )
    library_conventions_path = ROOT / "docs" / "開発" / "ライブラリ開発規約.md"
    library_conventions_text = library_conventions_path.read_text(encoding="utf-8").rstrip()

    reference_parts = [
        "# 1. コーディング規約（docs/開発/CONVENTIONS.md）\n" + conventions_text,
        "# 2. 公開 API 索引\n" + api_text.rstrip(),
    ]
    if examples_chunks:
        reference_parts.append("# 3. 動く実例（examples/）\n" + "".join(examples_chunks).rstrip())

    return [
        (
            "0_読み方",
            _bundle_readme(
                api_text, package_files, examples_files, impl_line_count, impl_byte_count
            ),
        ),
        ("1_規約_API索引_実例", "\n\n---\n\n".join(reference_parts)),
        ("2_実装全文", impl_text.rstrip()),
        (
            "3_エラー対応表_設計判断",
            "# エラー対応表（docs/ERRORS.md）\n"
            + errors_text.rstrip()
            + "\n\n---\n\n# 設計判断（docs/開発/仕様書.md）\n"
            + spec_text,
        ),
        (
            "4_新規プロジェクト向け",
            "# 新規プロジェクトのテンプレ\n"
            + new_project_text
            + "\n\n---\n\n# ライブラリ開発規約（docs/開発/ライブラリ開発規約.md）\n"
            + library_conventions_text,
        ),
    ]


def _bundle_readme(
    api_text: str,
    package_files: list[Path],
    examples_files: list[Path],
    impl_line_count: int,
    impl_byte_count: int,
) -> str:
    """``comken_bundle/`` の入口に置く「このフォルダの読み方」を組み立てる。"""
    public_api_names = sum(
        api_text.count(f"### `{name}`") for name in _extract_public_names(api_text)
    )
    lines = [
        "# comken_bundle/ — 社内 AI へ渡す comken 資料",
        "",
        "## このフォルダの読み方",
        "",
        "- comken は業務自動化の共通ライブラリです。",
        "- 章（規約・API索引・実例 → 実装全文 → エラー対応表・設計判断 →"
        " 新規プロジェクト向け）ごとにファイルを分けています。1章が数百万文字に"
        " なる場合は --max-chars（既定40万字）ごとに機械的に複数ファイルへ割ります"
        "（``_1of2`` のような接尾辞が付きます）。",
        "- **1_規約_API索引_実例 を必ず先に読んでください。** 命名・型ヒント・"
        "定数・例外・ロギングの書き方（コーディング規約）はここで固定されています。"
        "ここを読まずに書いたコードは規約違反で修正対象になります。公開APIも"
        "ここに載っているものだけを使ってください（``_`` 始まりは内部実装）。"
        "動く実例もここに含まれます。",
        "- 2_実装全文 は comken/ の全ソースです。索引に無い名前を勝手に使う前に"
        "ここで実在を確かめてください。",
        "- 3_エラー対応表_設計判断 は、利用者が読む画面の説明とその例外が送出される"
        "条件（エラー対応表）、「なぜその設計にしたか」（設計判断）です。",
        "- 4_新規プロジェクト向け は、comken を使う新しいツールのドキュメントを"
        "書くときのひな形と、comken **本体**を修正するときの規約です。"
        "comken を使うだけなら不要です。",
        "",
        "## 中身のサマリ",
        "",
        "- コーディング規約（CONVENTIONS.md）: あり",
        f"- 公開 API 索引の名前数: {public_api_names}",
        f"- 動く実例（examples/）のファイル数: {len(examples_files)}",
        f"- 実装全文（comken/）の .py ファイル数: {len(package_files)}",
        f"- 実装全文（comken/）の総行数: {impl_line_count:,}",
        f"- 実装全文（comken/）の総バイト数: {impl_byte_count:,}",
        "",
        "再生成: `python tools/export_for_chat.py`",
        "",
    ]
    return "\n".join(lines)


def _extract_public_names(api_text: str) -> set[str]:
    """API 索引テキストから ``### `Name`` 形式で現れる名前を抽出する。"""
    names: set[str] = set()
    for line in api_text.splitlines():
        if line.startswith("### `") and line.endswith("`"):
            names.add(line.removeprefix("### `").removesuffix("`"))
    return names


def _write_bundle(max_chars: int) -> None:
    """``comken_bundle/`` へ、章（カテゴリ）ごとにファイルを書き出す。

    1章が ``max_chars`` を超えるときだけ、``_split()`` でさらに複数ファイルへ割る。
    """
    if BUNDLE_OUTPUT_DIR.exists():
        shutil.rmtree(BUNDLE_OUTPUT_DIR)
    BUNDLE_OUTPUT_DIR.mkdir()
    for title, text in _bundle_sections():
        chunks = _split(text, max_chars)
        for number, chunk in enumerate(chunks, start=1):
            suffix = "" if len(chunks) == 1 else f"_{number}of{len(chunks)}"
            path = BUNDLE_OUTPUT_DIR / f"{title}{suffix}.md"
            header = "" if number == 1 else f"（{title} の続き {number}/{len(chunks)}）\n\n"
            path.write_text(header + chunk, encoding="utf-8")
            print(f"{path.name}  {len(chunk):,} 文字")  # noqa: T201


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-chars",
        type=int,
        default=DEFAULT_MAX_CHARS,
        help=(
            "comken_bundle/ の1章がこの文字数を超えたときの分割の目安"
            f"（既定 {DEFAULT_MAX_CHARS:,} 文字。0以下を指定すると分割を止める）"
        ),
    )
    args = parser.parse_args()
    bundle_max_chars = args.max_chars if args.max_chars > 0 else sys.maxsize
    API_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    API_OUTPUT_PATH.write_text(_api_text(), encoding="utf-8")
    print(f"{API_OUTPUT_PATH.relative_to(ROOT)} を生成しました")  # noqa: T201
    _write_errors()
    print(f"{ERRORS_OUTPUT_PATH.relative_to(ROOT)} を生成しました")  # noqa: T201
    _write_bundle(bundle_max_chars)
    print(f"{BUNDLE_OUTPUT_DIR.relative_to(ROOT)}/ に章ごとの資料を生成しました")  # noqa: T201


if __name__ == "__main__":
    main()
