"""社内 ChatGPT に貼り付けるためのテキストを書き出す。

ファイル添付（ZIP など）が使えない環境向け。目的ごとにドキュメントを連結し、
貼り付け1回分に収まるよう分割して `貼り付け用/` に出力する。

comken の公開 API は、機能カタログ（人が書いた説明）に加えて
`__all__` と AST から**署名だけ**を機械的に抜き出して添える。
説明だけだと ChatGPT が引数を推測で埋めてしまうため。

使い方:
    python export_for_chat.py                 # 既定の文字数で分割して出力
    python export_for_chat.py --max-chars 8000
"""

from __future__ import annotations

import argparse
import ast
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = ROOT / "comken"
OUTPUT_DIR = ROOT / "貼り付け用"

# 1回の貼り付けに収める目安。社内 ChatGPT の入力欄の上限が分からないため、
# どの環境でも通りやすい控えめな値を既定にしている（--max-chars で変更可）。
DEFAULT_MAX_CHARS = 20000

# 出力ファイル名 → (ChatGPT に伝える役割, 連結する資料)
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
        ["docs/機能カタログ.md", "@API署名"],
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


DOC_SECTION_HEADS = ("Args:", "Returns:", "Raises:", "Yields:", "Note:")


def _first_doc_line(node: ast.AST) -> str:
    """docstring の要約（1行目）を返す（無ければ空文字）。"""
    doc = ast.get_docstring(node) or ""
    for line in doc.splitlines():
        summary = line.strip()
        # 要約を書かず Args: から始まる docstring があるため、見出しは要約とみなさない。
        if summary and not summary.startswith(DOC_SECTION_HEADS):
            return summary
    return ""


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """関数定義から本文を落とし、シグネチャだけの1行を作る。"""
    # NOTE: 本文を `...` に差し替えて unparse すると、引数・型ヒント・デコレーターを
    #       自前で組み立てずに済む。
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
    """`__all__ = [...]` に並んだ名前を返す。"""
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "__all__" in targets and isinstance(node.value, ast.List):
            return [e.value for e in node.value.elts if isinstance(e, ast.Constant)]
    return []


def _import_origins(tree: ast.Module, package_dir: Path) -> dict[str, Path]:
    """`from .module import X` を読み、名前 → 定義元ファイルの対応を作る。"""
    origins: dict[str, Path] = {}
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or node.level != 1 or not node.module:
            continue
        source = package_dir.joinpath(*node.module.split("."))
        path = source.with_suffix(".py")
        if not path.exists():
            path = source / "__init__.py"  # サブパッケージからの再輸出
        if path.exists():
            for alias in node.names:
                origins[alias.asname or alias.name] = path
    return origins


def _class_text(node: ast.ClassDef) -> list[str]:
    """クラスを「1行説明 + 公開メソッドの署名」に畳んだ行を返す。"""
    # 継承元は例外の捕捉範囲を判断する材料になるので残す。
    bases = ", ".join(ast.unparse(base) for base in node.bases)
    lines = [f"class {node.name}({bases}):" if bases else f"class {node.name}:"]
    if summary := _first_doc_line(node):
        lines.append(f"    # {summary}")
    for child in node.body:
        if not isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        # 内部実装は渡さない。`__init__` は呼び出し方そのものなので例外的に載せる。
        if child.name.startswith("_") and child.name != "__init__":
            continue
        # デコレーター付きは複数行になるため、全行をまとめて字下げする。
        lines += [f"    {line}" for line in _signature(child).splitlines()]
        if summary := _first_doc_line(child):
            lines.append(f"        # {summary}")
    if len(lines) == 1:
        lines.append("    ...")  # 例外クラスなど、中身が無いもの
    return lines


def _api_text() -> str:
    """`__all__` に載っている公開 API の署名一覧を組み立てる。"""
    sections: list[str] = [
        "# comken 公開 API 署名一覧（自動生成）",
        "",
        "各パッケージの `__all__` に載っているものだけを列挙している。",
        "ここに無い名前は公開 API ではないので、import しないこと。",
        "`#` の行はその関数・クラスの説明。",
    ]
    for init_path in sorted(PACKAGE_ROOT.rglob("__init__.py")):
        tree = ast.parse(init_path.read_text(encoding="utf-8"))
        names = _all_names(tree)
        if not names:
            continue
        package = ".".join(init_path.parent.relative_to(ROOT).parts)
        origins = _import_origins(tree, init_path.parent)
        sections += ["", "-" * 60, f"## from {package} import ...", ""]

        # 定義元ごとにまとめると、関連する API が並んで読みやすい。
        for name in names:
            path = origins.get(name)
            if path is None:
                sections.append(f"{name}  # {package} で定義")
                continue
            definition = _definition(path, name)
            sections += definition if definition else [f"{name}"]
    return "\n".join(sections) + "\n"


def _definition(path: Path, name: str) -> list[str]:
    """モジュールから `name` の定義を探し、署名の行を返す。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return [*_class_text(node), ""]
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name:
            lines = [_signature(node)]
            if summary := _first_doc_line(node):
                lines.append(f"    # {summary}")
            return [*lines, ""]
    return []


def _bundle_text(title: str, purpose: str, sources: list[str]) -> str:
    """1つの貼り付け用テキストを組み立てる。"""
    parts = [f"# {title}", "", purpose, ""]
    for source in sources:
        if source == "@API署名":
            parts += ["", "=" * 60, "", _api_text()]
            continue
        parts += ["", "=" * 60, f"（資料: {source}）", "=" * 60, ""]
        parts.append((ROOT / source).read_text(encoding="utf-8-sig").rstrip())
    return "\n".join(parts) + "\n"


def _split(text: str, max_chars: int) -> list[str]:
    """行の途中で切らずに、指定文字数を目安に分割する。"""
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.splitlines(keepends=True):
        if current and size + len(line) > max_chars:
            chunks.append("".join(current))
            current, size = [], 0
        current.append(line)
        size += len(line)
    if current:
        chunks.append("".join(current))
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-chars",
        type=int,
        default=DEFAULT_MAX_CHARS,
        help=f"1ファイルの目安の文字数（既定 {DEFAULT_MAX_CHARS}）",
    )
    args = parser.parse_args()

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir()

    for title, (purpose, sources) in BUNDLES.items():
        chunks = _split(_bundle_text(title, purpose, sources), args.max_chars)
        for number, chunk in enumerate(chunks, start=1):
            suffix = "" if len(chunks) == 1 else f"_{number}of{len(chunks)}"
            path = OUTPUT_DIR / f"{title}{suffix}.txt"
            header = "" if number == 1 else f"（{title} の続き {number}/{len(chunks)}）\n\n"
            path.write_text(header + chunk, encoding="utf-8")
            print(f"{path.name}  {len(chunk):,} 文字")  # noqa: T201


if __name__ == "__main__":
    main()
