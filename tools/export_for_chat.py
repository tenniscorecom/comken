"""comken の公開 API ドキュメント、エラー対応ガイド、貼り付け用資料を生成する。

**このファイルは開発用**（リポジトリ直下の ``tools/`` にあり、配布されない）。
``comken/tools/`` に同梱されて ``python -m comken init`` から呼ばれる
``new_project.py`` とは役割が違うので、混同しないこと。

各パッケージの ``__all__`` をたどり、型ヒント付き署名と docstring 全文を
``docs/自動生成/API.md`` へ書き出す。添付できない環境では ``--max-chars`` を指定すると、
従来どおり資料を文字数の目安で分割して ``貼り付け用/`` へ出力する。

**同時に、社内の外部 AI へ貼るための 1 ファイル資料（``comken_bundle.md``）も
既定で生成する。** インデックス → 実例 → 実装全文 → エラー対応表の順で並び、
内部実装を区別せずに使ったサンプルが出にくくなっている。

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
BUNDLE_OUTPUT_PATH = ROOT / "comken_bundle.md"
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
            exceptions.InternalLibraryError,
        ),
    ),
    ErrorCategory("ブラウザ（Edge 自動操作）のエラー", (exceptions.BrowserError,)),
    ErrorCategory("Table のエラー", (exceptions.TableError,)),
    ErrorCategory("Windows 操作のエラー", (exceptions.WindowNotFoundError,)),
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
    exceptions.InternalLibraryError,
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


def _legacy_bundle_text(title: str, purpose: str, sources: list[str]) -> str:
    """貼り付け用資料1種類（``--max-chars`` 向け）のテキストを組み立てる。"""
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
        chunks = _split(_legacy_bundle_text(title, purpose, sources), max_chars)
        for number, chunk in enumerate(chunks, start=1):
            suffix = "" if len(chunks) == 1 else f"_{number}of{len(chunks)}"
            path = LEGACY_OUTPUT_DIR / f"{title}{suffix}.txt"
            header = "" if number == 1 else f"（{title} の続き {number}/{len(chunks)}）\n\n"
            path.write_text(header + chunk, encoding="utf-8")
            print(f"{path.name}  {len(chunk):,} 文字")  # noqa: T201


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


def _verify_internal_library_placeholder() -> None:
    """社内ライブラリ仮名が保たれているか検証する。

    ``comken/toolbox/rpa.py`` の ``RPA_LIBRARY_NAME`` が
    ``kensetsu_libs.`` で始まる仮名のまま（実名へ書き戻されていないこと）を
    確認する。実名に置き換わっていると、公開リポジトリ経由で社内ライブラリ
    名が社外へ漏れるため、生成を止める。

    Salesforce は comken 自前の ``comken/toolbox/salesforce/`` を使うため、
    社内ライブラリ経由の ``SALESFORCE_LIBRARY_NAME`` の検証は不要になった。

    旧 ``internal`` 層にあった共通ルート定数は廃止された（バージョンを含まない
    仮名で確定したため）。さらに社内ライブラリ呼び出し層（``internal``）自体も
    廃止され ``toolbox`` へ統合されたため、各モジュールの定数を直接見る。

    Raises:
        RuntimeError: 仮名が崩れていた場合。
    """
    expected_prefix = "kensetsu_libs."
    rpa_module = import_module("comken.toolbox.rpa")
    names: list[tuple[str, str]] = [
        ("RPA_LIBRARY_NAME", rpa_module.RPA_LIBRARY_NAME),
    ]
    bad = [(label, value) for label, value in names if not value.startswith(expected_prefix)]
    if bad:
        details = ", ".join(f"{label}={value!r}" for label, value in bad)
        raise RuntimeError(
            "社内ライブラリ仮名が壊れています。"
            f"{details} が {expected_prefix!r} で始まっていません。"
            "comken は公開リポジトリのため、社内ライブラリの実名が混入しないよう"
            f"仮名 {expected_prefix!r} を保ってください。"
        )


def _bundle_text() -> str:
    """社外 AI へ貼るための 1 ファイル資料を組み立てる。

    並び順は **ヘッダ → コーディング規約 → 公開 API 索引 → 動く実例
    (examples/) → 実装全文 (comken/) → エラー対応表 → 設計判断**。
    規約を 1 章目に置くのは、社外 AI に規約（命名・型ヒント・定数・例外・
    ロギング）を最初に読ませて、生成コードの表記ブレや規約違反を防ぐため。
    その後は索引で公開 API を固定してから実例で正しい書き方を見せ、最後に
    全文とエラー表・仕様書で細部を裏取る構成にする。

    社内ライブラリ仮名が保たれているかは ``_verify_internal_library_placeholder``
    で先に検証する（生成途中で発見しても中途半端なファイルが残るのを避ける）。
    """
    _verify_internal_library_placeholder()

    conventions_path = ROOT / "docs" / "開発" / "CONVENTIONS.md"
    spec_path = ROOT / "docs" / "開発" / "仕様書.md"
    conventions_text = conventions_path.read_text(encoding="utf-8").rstrip()
    spec_text = spec_path.read_text(encoding="utf-8").rstrip()
    spec_line_count = len(spec_text.splitlines())

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

    parts: list[str] = []
    parts.append(
        _bundle_header(
            api_text,
            package_files,
            examples_files,
            impl_line_count,
            impl_byte_count,
            spec_line_count,
        )
    )
    parts.append("\n---\n\n")
    parts.append("# 1. コーディング規約（docs/開発/CONVENTIONS.md）\n")
    parts.append(conventions_text)
    parts.append("\n---\n\n")
    parts.append("# 2. 公開 API 索引\n")
    parts.append(api_text.rstrip())
    parts.append("\n---\n\n")
    if examples_chunks:
        parts.append("# 3. 動く実例（examples/）\n")
        parts.extend(examples_chunks)
        parts.append("\n---\n\n")
    parts.append("# 4. 実装全文（comken/）\n")
    parts.append(impl_text)
    parts.append("\n---\n\n")
    parts.append("# 5. エラー対応表（docs/ERRORS.md）\n")
    parts.append(errors_text.rstrip())
    parts.append("\n---\n\n")
    parts.append("# 6. 設計判断（docs/開発/仕様書.md）\n")
    parts.append(spec_text)
    parts.append("\n")
    return "".join(parts)


def _bundle_header(
    api_text: str,
    package_files: list[Path],
    examples_files: list[Path],
    impl_line_count: int,
    impl_byte_count: int,
    spec_line_count: int,
) -> str:
    """``comken_bundle.md`` の冒頭に置く「このファイルの読み方」を組み立てる。"""
    public_api_names = sum(
        api_text.count(f"### `{name}`") for name in _extract_public_names(api_text)
    )
    lines = [
        "# comken_bundle.md — 社内 AI へ渡す comken 資料",
        "",
        "## このファイルの読み方",
        "",
        "- comken は業務自動化の共通ライブラリです。",
        "- このファイル 1 つだけで資料が完結します（コーディング規約 → API 索引 → 実例"
        " → 実装全文 → エラー対応表 → 設計判断）。",
        "- **第 1 章のコーディング規約を必ず先に読んでください。** 命名・型ヒント・"
        "定数・例外・ロギングの書き方はここで固定されています。ここを読まずに書いた"
        "コードは規約違反で修正対象になります。",
        "- 公開 API は **第 2 章** の索引に載っているものだけを使ってください。"
        "``_`` 始まりは内部実装なので使わないこと。",
        "- 第 3 章は **動く実例** です。サンプルコードを書くときはここを参照してください。",
        "- 第 4 章は実装全文です。索引に無い名前を勝手に使う前にここで実在を確かめてください。",
        "- 第 5 章はエラー対応表です。利用者が読む画面の説明と、その例外が送出される条件を"
        " ここで確認できます。",
        "- 第 6 章は設計判断（仕様書）です。「なぜその設計にしたか」を知りたいときはここを"
        " 参照してください。",
        "",
        "## 中身のサマリ",
        "",
        "- コーディング規約（CONVENTIONS.md）: あり",
        f"- 公開 API 索引の名前数: {public_api_names}",
        f"- 動く実例（examples/）のファイル数: {len(examples_files)}",
        f"- 実装全文（comken/）の .py ファイル数: {len(package_files)}",
        f"- 実装全文（comken/）の総行数: {impl_line_count:,}",
        f"- 実装全文（comken/）の総バイト数: {impl_byte_count:,}",
        f"- 設計判断（仕様書.md）の行数: {spec_line_count:,}",
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


def _write_bundle() -> None:
    """``comken_bundle.md`` を 1 ファイル書き出す。"""
    text = _bundle_text()
    BUNDLE_OUTPUT_PATH.write_text(text, encoding="utf-8")
    print(  # noqa: T201
        f"{BUNDLE_OUTPUT_PATH.relative_to(ROOT)} を生成しました"
        f"（{len(text):,} 文字 / {BUNDLE_OUTPUT_PATH.stat().st_size:,} バイト）"
    )


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
    _write_bundle()


if __name__ == "__main__":
    main()
