"""文書のコード例・リンク・公開 API 一覧が実装と食い違っていないか検証する。

サンプルコードは環境（Excel・ブラウザ）がないと実行まではできないため、
ここでは compile() による構文チェックを行う（タイプミス・インデント崩れ・未閉じ括弧を検出）。
実際に動くことの担保は test_examples.py（オフライン例の実行）が担う。
"""

import ast
import re
from pathlib import Path

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
    "salesforce",
    "credentials",
    "pdf",
    "setup_logger",
    "ExcelFile",
    "set_dry_run",
    "set_debug",
    "FileNameBuilder",
    "cleanup_stale_tmp",
)


def _python_blocks() -> list:
    blocks = []
    for doc in _DOCS:
        if not doc.exists():
            continue
        for i, match in enumerate(_CODE_BLOCK.finditer(doc.read_text(encoding="utf-8"))):
            blocks.append(pytest.param(match.group(1), id=f"{doc.name}#{i + 1}"))
    return blocks


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
    guide = (_ROOT / "ERRORS.md").read_text(encoding="utf-8")
    names = _all_names(_ROOT / "comken" / "exceptions" / "__init__.py")

    assert len(names) == 32
    assert not [name for name in names if f"`{name}`" not in guide]


def test_feature_catalog_covers_all_public_api():
    catalog = (_ROOT / "docs" / "機能カタログ.md").read_text(encoding="utf-8")
    init_files = [
        _ROOT / "comken" / "__init__.py",
        *(_ROOT / "comken").glob("*/__init__.py"),
        _ROOT / "comken" / "utils" / "files" / "__init__.py",
    ]
    names = []
    for path in init_files:
        if path.parent.name == "exceptions":
            continue
        names.extend(name for name in _all_names(path) if name not in names)

    assert len(names) == 52
    assert not [name for name in names if name not in catalog]


@pytest.mark.parametrize("doc", _DOCS, ids=lambda path: str(path.relative_to(_ROOT)))
def test_removed_names_do_not_remain_in_docs(doc):
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
