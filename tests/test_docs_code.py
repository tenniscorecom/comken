"""文書のコード例・リンク・公開 API 一覧が実装と食い違っていないか検証する。

サンプルコードは環境（Excel・ブラウザ）がないと実行まではできないため、
ここでは compile() による構文チェックを行う（タイプミス・インデント崩れ・未閉じ括弧を検出）。
実際に動くことの担保は test_examples.py（オフライン例の実行）が担う。
"""

import ast
import importlib
import re
from pathlib import Path

import export_for_chat
import pytest

_ROOT = Path(__file__).resolve().parent.parent
_DOCS = [
    path
    for path in _ROOT.rglob("*.md")
    if ".git" not in path.parts and path.name != "CODEX_TASK.md"
]

_CODE_BLOCK = re.compile(r"```python\n(.*?)```", re.DOTALL)
_MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]*]\(([^)]+)\)")
_HEADING = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
_REMOVED_NAMES = (
    "pdf",
    "setup_logger",
    "ExcelFile",
    "set_dry_run",
    "set_debug",
    "FileNameBuilder",
    "cleanup_stale_tmp",
    "transfer_by_key",
    "used_last_row",
    "count_a",
)


def _python_blocks() -> list:
    blocks = []
    for doc in _DOCS:
        if not doc.exists():
            continue
        for i, match in enumerate(_CODE_BLOCK.finditer(doc.read_text(encoding="utf-8"))):
            blocks.append(pytest.param(match.group(1), id=f"{doc.name}#{i + 1}"))
    return blocks


def test_all_comken_modules_start_docstring_with_their_path() -> None:
    """全モジュールを開いた瞬間に、どのファイルの説明か判断できる。"""
    missing = []
    for path in sorted((_ROOT / "comken").rglob("*.py")):
        relative_path = path.relative_to(_ROOT).as_posix()
        docstring = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8")), clean=False)
        first_line = docstring.splitlines()[0] if docstring else ""
        if not first_line.startswith(f"{relative_path} — "):
            missing.append(relative_path)
    assert not missing, f"先頭docstringにファイルパスがありません: {missing}"


def test_all_named_comken_classes_and_functions_have_docstrings() -> None:
    """利用者が名前から辿るクラス・関数には説明を必須にする。"""
    missing = []
    for path in sorted((_ROOT / "comken").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("_"):
                continue
            if ast.get_docstring(node) is None:
                missing.append(f"{path.relative_to(_ROOT).as_posix()}:{node.lineno} {node.name}")
    assert not missing, f"docstringがないクラス・関数があります: {missing}"


@pytest.mark.parametrize("code", _python_blocks())
def test_python_code_block_compiles(code):
    """ドキュメントの ```python ブロックが構文エラーなくコンパイルできる。"""
    # 抜粋（... で省略した）説明用スニペットは構文が通らないので対象外にする
    if "..." in code:
        pytest.skip("説明用の抜粋スニペット")
    compile(code, "<doc>", "exec")


def _all_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
        ):
            return ast.literal_eval(node.value)
    return []


def _anchor(heading: str) -> str:
    """GitHub Markdown と同じ要領で、見出しからリンク用アンカーを作る。"""
    heading = re.sub(r"[^\w\s-]", "", heading.lower())
    return re.sub(r"\s+", "-", heading.strip())


def test_exception_guide_covers_all_public_exceptions():
    guide = (_ROOT / "docs" / "ERRORS.md").read_text(encoding="utf-8")
    names = _all_names(_ROOT / "comken" / "exceptions" / "__init__.py")

    # NOTE: 件数は直書きしない。下の網羅チェックで目的は満たせており、
    #       件数だけ固定すると API を1つ足すたびに無関係な失敗が出る。
    assert names, "公開例外を読み取れていない（__all__ の解析に失敗している）"
    assert not [name for name in names if f"`{name}`" not in guide]
    assert guide == export_for_chat._merged_errors_text(guide)


def test_all_public_exceptions_have_treatment():
    """例外追加時に、非エンジニア向けの対処を書き忘れていない。"""
    names = _all_names(_ROOT / "comken" / "exceptions" / "__init__.py")
    missing = []
    for name in names:
        exception = getattr(export_for_chat.exceptions, name)
        try:
            export_for_chat._exception_details(exception)
        except ValueError:
            missing.append(name)
    assert not missing


def _parse_tree_line(line: str) -> tuple[int, str] | None:
    """ツリー1行を (level, name) に分解する。ツリー行でなければ None。"""
    prefix_len = 0
    while line[prefix_len : prefix_len + 4] == "│   ":
        prefix_len += 4
    rest = line[prefix_len:]

    if rest.startswith("├── ") or rest.startswith("└── "):
        return prefix_len // 4 + 1, rest[4:].split()[0]

    stripped = line.strip()
    if not stripped:
        return None  # 空行はスキップ
    # ルート候補（マーカー無し・非空）— 呼び出し側で「最初の1件だけ」を管理する
    return 0, stripped.split()[0]


def _parse_exception_tree(docstring: str) -> tuple[dict[str, str | None], str | None]:
    """`comken/exceptions/__init__.py` の冒頭 docstring ツリーを解析する。

    解析ルール:
        - ツリーはファイル説明文の直後の **空行以降** から始まる
        - 行頭の `│   ` を1段のインデントとする（ASCII 罫線の縦線）
        - `├── ` / `└── ` の次の単語が例外名（後ろのコメントは読み飛ばす）
        - ルート（`ComkenError`）はインデント無しで1行だけ

    Returns:
        (parent_map, root_name)
        parent_map: 例外名 → 親クラス名（ルートは None）
        root_name: ルート（`ComkenError` であるべき）
    """
    parent: dict[str, str | None] = {}
    root: str | None = None
    stack: list[tuple[str, int]] = []  # (name, level)
    started = False  # 最初の空行を過ぎてからツリーが始まる

    for line in docstring.splitlines():
        if not started:
            if not line.strip():
                started = True
            continue

        parsed = _parse_tree_line(line)
        if parsed is None:
            continue  # ツリー末尾の空行など
        level, _name = parsed

        if level == 0:
            # ルート候補: 先頭の1件だけ採用し、以降の非マーカー行は読み飛ばす
            if root is not None:
                continue
            name = _name
            root = name
        else:
            name = _name

        while stack and stack[-1][1] >= level:
            stack.pop()

        if stack:
            parent[name] = stack[-1][0]
        else:
            parent[name] = None
            if root is None:
                root = name

        stack.append((name, level))

    return parent, root


def test_exception_docstring_tree_matches_public_api():
    """`comken/exceptions/__init__.py` の冒頭 docstring ツリーが、
    `__all__` の例外名集合と**完全に一致**し、
    ツリーが表す継承関係が実際の継承関係と一致することを検証する。
    """
    init = _ROOT / "comken" / "exceptions" / "__init__.py"
    tree = ast.parse(init.read_text(encoding="utf-8"))
    docstring = ast.get_docstring(tree, clean=False)
    assert docstring is not None, "exceptions/__init__.py の冒頭に docstring がない"

    parent, root = _parse_exception_tree(docstring)

    expected_names = set(_all_names(init))
    tree_names = set(parent)

    missing_in_tree = expected_names - tree_names
    extra_in_tree = tree_names - expected_names
    assert not missing_in_tree, f"docstring ツリーに無い公開例外: {sorted(missing_in_tree)}"
    assert not extra_in_tree, (
        f"docstring ツリーにだけある名前（__all__ に無い）: {sorted(extra_in_tree)}"
    )

    assert root is not None, "docstring ツリーのルート（先頭のインデント無し行）が見つからない"
    assert root == "ComkenError", f"ルートは ComkenError であるべき、実際: {root!r}"

    exceptions_module = importlib.import_module("comken.exceptions")
    for name, declared_parent in parent.items():
        cls = getattr(exceptions_module, name)
        actual_parent_name = cls.__bases__[0].__name__
        if name == root:
            assert declared_parent is None, (
                f"ルート {name} にツリー上で親が書かれている: {declared_parent}"
            )
            assert actual_parent_name == "Exception", (
                f"ルート {name} の継承元が Exception ではない: {actual_parent_name}"
            )
            continue
        assert declared_parent is not None, f"{name} はツリー上で親の下に書かれているべき"
        assert actual_parent_name == declared_parent, (
            f"{name} は {actual_parent_name} を継承しているが、"
            f"ツリーでは {declared_parent} の下にある"
        )


def test_error_guide_generation_is_idempotent_and_preserves_handwritten_part():
    """再生成を繰り返しても同じで、マーカーより上は変更しない。"""
    handwritten = "# 手書きの前書き\n\nこの内容は残す。"
    source = f"{handwritten}\n\n{export_for_chat.ERRORS_GENERATED_MARKER}\n\n古い生成部分\n"
    generated_once = export_for_chat._merged_errors_text(source)
    generated_twice = export_for_chat._merged_errors_text(generated_once)

    assert generated_once == generated_twice
    preserved = generated_once.split(export_for_chat.ERRORS_GENERATED_MARKER, maxsplit=1)[0]
    assert preserved.rstrip() == handwritten


def test_error_guide_generation_requires_marker():
    """マーカーがない文書を黙って上書きしない。"""
    with pytest.raises(ValueError, match="自動生成マーカーがありません"):
        export_for_chat._merged_errors_text("# 手書きだけのガイド\n")


def test_generated_api_covers_all_public_api():
    api = (_ROOT / "docs" / "自動生成" / "API.md").read_text(encoding="utf-8")
    init_files = [
        _ROOT / "comken" / "__init__.py",
        *(_ROOT / "comken").glob("*/__init__.py"),
        *(_ROOT / "comken" / "toolbox").glob("*/__init__.py"),
        *(_ROOT / "comken" / "services").glob("*/__init__.py"),
        _ROOT / "comken" / "core" / "files" / "__init__.py",
    ]
    names = []
    for path in init_files:
        if path.parent.name == "exceptions":
            continue
        names.extend(name for name in _all_names(path) if name not in names)

    assert names, "公開 API を読み取れていない（__all__ の解析に失敗している）"
    assert not [name for name in names if f"`{name}`" not in api]


@pytest.mark.parametrize("doc", _DOCS, ids=lambda path: str(path.relative_to(_ROOT)))
def test_removed_names_do_not_remain_in_docs(doc):
    if doc.name == "API.md":
        pytest.skip("docstring 全文から作る生成物では、通常語や例外名の部分一致を許容する")
    text = doc.read_text(encoding="utf-8")
    found = [
        name
        for name in _REMOVED_NAMES
        if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text, re.IGNORECASE)
    ]
    assert not found


@pytest.mark.parametrize("doc", _DOCS, ids=lambda path: str(path.relative_to(_ROOT)))
def test_markdown_relative_links_resolve(doc):
    text = doc.read_text(encoding="utf-8")
    headings = {_anchor(heading) for heading in _HEADING.findall(text)}

    for raw_target in _MARKDOWN_LINK.findall(text):
        target = raw_target.strip("<>")
        if "://" in target:
            continue

        file_part, _, anchor = target.partition("#")
        linked_doc = doc if not file_part else (doc.parent / file_part).resolve()
        assert linked_doc.exists(), f"{doc}: リンク先がありません: {target}"

        if anchor and linked_doc.suffix.lower() == ".md":
            linked_text = linked_doc.read_text(encoding="utf-8")
            linked_headings = (
                headings
                if linked_doc == doc
                else {_anchor(heading) for heading in _HEADING.findall(linked_text)}
            )
            assert anchor in linked_headings, f"{doc}: アンカーがありません: {target}"
