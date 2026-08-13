"""comken の公開 API ドキュメントと、貼り付け用資料を生成する。

通常は各パッケージの ``__all__`` をたどり、型ヒント付き署名と docstring 全文を
``docs/API.md`` へ書き出す。添付できない環境では ``--max-chars`` を指定すると、
従来どおり資料を文字数の目安で分割して ``貼り付け用/`` へ出力する。

使い方:
    python export_for_chat.py
    python export_for_chat.py --max-chars 20000
"""

from __future__ import annotations

import argparse
import ast
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = ROOT / "comken"
API_OUTPUT_PATH = ROOT / "docs" / "API.md"
LEGACY_OUTPUT_DIR = ROOT / "貼り付け用"

BUNDLES: dict[str, tuple[str, list[str]]] = {
    "1_コーディング規約": (
        "これは社内 Python ライブラリ comken を使うツールの**コーディング規約**です。"
        "以後このスレッドで書くコードは、この規約に従ってください。",
        ["CONVENTIONS.md", "docs/プロジェクト規約.md"],
    ),
    "2_ライブラリの使い方": (
        "これは社内 Python ライブラリ comken の**API 一覧**です。"
        "comken を使うコードを書くときは、ここに載っている関数・引数だけを使ってください。"
        "載っていない機能は「comken には無い」と判断し、勝手に作らず標準ライブラリで書くか、"
        "その旨を伝えてください。",
        ["docs/機能カタログ.md", "@API"],
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
        ["docs/ライブラリ開発規約.md"],
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
    """相対 import の参照先 Python ファイルを返す。"""
    if node.level != 1 or not node.module:
        return None
    source = package_file.parent.joinpath(*node.module.split("."))
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


def _doc_lines(node: ast.AST, heading_level: int) -> list[str]:
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
    API_OUTPUT_PATH.write_text(_api_text(), encoding="utf-8")
    print(f"{API_OUTPUT_PATH.relative_to(ROOT)} を生成しました")  # noqa: T201
    if args.max_chars is not None:
        _write_legacy_bundles(args.max_chars)


if __name__ == "__main__":
    main()
