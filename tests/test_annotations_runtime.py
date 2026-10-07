"""``TYPE_CHECKING`` だけで import した名前を、Python 3.13 で定義時に
評価される型注釈に使っていないかを ``comken/`` パッケージ全体に対して
静的に検査する。

comken の ``requires-python`` は ``>=3.13``。3.13 では関数の注釈は定義時に
そのまま評価されるので、``if TYPE_CHECKING:`` の中でだけ import した名前を
注釈に書くと ``NameError`` で実行時クラッシュする。3.14 では PEP 649 により
関数の注釈は遅延評価されるので、3.14 で動かすだけでは pytest も pyright も
この違反をすり抜ける。また、テストから import されないモジュールは pytest の
カバー範囲外なので、CI を 3.13 で回しても見つからない。
この静的検査は、その両方（3.14 での取りこぼし、テストから import されない
モジュール）を pytest で検出する。文字列注釈や ``from __future__ import annotations`` が
付いたファイルは評価されないので対象外、関数本体の中の ``AnnAssign``
（ローカル変数の注釈）も評価されないので対象外。

同様の検査違反は Salesforceレポートダウンローダー（commit 7fdc9a8）
でも実際に起きている。

注意: 定義中のクラス自身を注釈に使う誤り（クラス本体が評価されるときに
まだ未束縛のクラスを参照するケース、comken でも過去に 13 件あった）は
この検査の対象外。
"""

import ast
from pathlib import Path

import pytest

# ── AST ヘルパー ────────────────────────────────────────────────────


def _has_future_annotations(tree: ast.Module) -> bool:
    """``from __future__ import annotations`` がモジュール先頭にあるか。"""
    for stmt in tree.body:
        if (
            isinstance(stmt, ast.ImportFrom)
            and stmt.module == "__future__"
            and any(alias.name == "annotations" for alias in stmt.names)
        ):
            return True
    return False


def _is_type_checking_guard(test: ast.expr) -> bool:
    """``if TYPE_CHECKING:`` / ``if typing.TYPE_CHECKING:`` の条件か。"""
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    return (
        isinstance(test, ast.Attribute)
        and test.attr == "TYPE_CHECKING"
        and isinstance(test.value, ast.Name)
        and test.value.id == "typing"
    )


def _names_from_import(stmt: ast.stmt) -> set[str]:
    """``import`` / ``from ... import ... as ...`` 1 つから、束縛される名前の集合。"""
    names: set[str] = set()
    if isinstance(stmt, ast.Import):
        for alias in stmt.names:
            top = alias.name.split(".", 1)[0]
            names.add(alias.asname or top)
    elif isinstance(stmt, ast.ImportFrom):
        for alias in stmt.names:
            names.add(alias.asname or alias.name)
    return names


def _collect_type_checking_names(tree: ast.Module) -> set[str]:
    """モジュール直下の ``if TYPE_CHECKING:`` ブロック内で束縛された名前の集合。"""
    names: set[str] = set()
    for stmt in tree.body:
        if isinstance(stmt, ast.If) and _is_type_checking_guard(stmt.test):
            for inner in stmt.body:
                names.update(_names_from_import(inner))
    return names


def _is_string_annotation(node: ast.expr) -> bool:
    """文字列リテラル注釈（``"X"`` / ``'X'``）は評価されないので中身は見ない。"""
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _function_annotations(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.expr]:
    """関数の引数注釈（posonly/args/vararg/kwonly/kwarg）と戻り値注釈を平坦に返す。

    文字列注釈はスキップする。
    """
    args = fn.args
    out: list[ast.expr] = []
    for arg in (
        *args.posonlyargs,
        *args.args,
        *([args.vararg] if args.vararg else []),
        *args.kwonlyargs,
        *([args.kwarg] if args.kwarg else []),
    ):
        if arg.annotation is not None and not _is_string_annotation(arg.annotation):
            out.append(arg.annotation)
    if fn.returns is not None and not _is_string_annotation(fn.returns):
        out.append(fn.returns)
    return out


def _names_in_annotation(annotation: ast.expr) -> list[tuple[str, int]]:
    """注釈 AST 内の ``ast.Name``（属性チェーンの根を含む）の ``(id, 行番号)`` を返す。"""
    return [(node.id, node.lineno) for node in ast.walk(annotation) if isinstance(node, ast.Name)]


def _collect_violations(tree: ast.Module) -> list[tuple[int, str]]:
    """定義時に評価される注釈中の ``TYPE_CHECKING`` 名を ``(行番号, 名前)`` で列挙する。

    - ``from __future__ import annotations`` 付きのファイルは対象外
    - 関数本体内の ``AnnAssign``（ローカル変数の注釈）は評価されないので対象外
    - 文字列注釈は中身を見ない
    - 同じ ``(行番号, 名前)`` の重複は1件にまとめる（``dict[type[X], X]`` のように
      同じ行で同じ名前が複数回現れるケース）。順序は行番号 → 名前で安定。
    """
    type_checking_names = _collect_type_checking_names(tree)
    if not type_checking_names or _has_future_annotations(tree):
        return []

    # 同じ (行番号, 名前) は 1 件にまとめる
    seen: set[tuple[int, str]] = set()
    visitor = _AnnotationVisitor(type_checking_names, seen)
    visitor.visit(tree)
    return sorted(seen)


class _AnnotationVisitor:
    """モジュールの AST を走査して、定義時に評価される注釈中の ``TYPE_CHECKING`` 名を集める。

    ヘルパーに分けないと分岐が膨らんで C901（複雑度 10 以下）に違反するため、状態をクラスに
    集約して 1 ノード種別ごとの処理をメソッドに切り出している。
    """

    def __init__(self, type_checking_names: set[str], seen: set[tuple[int, str]]) -> None:
        self._type_checking_names = type_checking_names
        self._seen = seen

    def visit(self, node: ast.AST, in_function: bool = False) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self._visit_function(node)
            return
        if isinstance(node, ast.AnnAssign):
            self._visit_annassign(node, in_function)
            return
        if isinstance(node, ast.ClassDef):
            # クラス本体は定義時に評価される（関数の内側に class があっても）。
            # 配下の AnnAssign を拾うために in_function=False で再帰
            self._visit_children(node, in_function=False)
            return
        # if / try / with / for などの構文は子をそのまま再帰（in_function は維持）
        self._visit_children(node, in_function=in_function)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        # 関数の引数・戻り値の注釈は定義時に評価される
        for annotation in _function_annotations(node):
            self._check(annotation)
        # 本体の中の AnnAssign は関数ローカル変数の注釈扱い（評価されない）なので
        # in_function=True で配下を再帰
        self._visit_children(node, in_function=True)

    def _visit_annassign(self, node: ast.AnnAssign, in_function: bool) -> None:
        # 関数外の注釈だけ評価される。クラス本体は定義時に評価されるので対象
        if not in_function and not _is_string_annotation(node.annotation):
            self._check(node.annotation)

    def _visit_children(self, node: ast.AST, *, in_function: bool) -> None:
        for child in ast.iter_child_nodes(node):
            self.visit(child, in_function)

    def _check(self, annotation: ast.expr) -> None:
        for name, line in _names_in_annotation(annotation):
            if name in self._type_checking_names:
                self._seen.add((line, name))


# ── ソースツリー走査 ────────────────────────────────────────────────


def _collect_comken_violations(root: Path) -> list[tuple[Path, int, str]]:
    """``root/comken/`` 配下の全 .py を検査し、違反を ``(相対パス, 行番号, 名前)`` で列挙する。"""
    package_root = root / "comken"
    results: list[tuple[Path, int, str]] = []
    for path in sorted(package_root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for line, name in _collect_violations(tree):
            results.append((path.relative_to(root), line, name))
    return results


# ── テスト本体 ─────────────────────────────────────────────────────


def test_no_type_checking_only_names_used_in_runtime_annotations() -> None:
    """``comken/`` パッケージ全体で ``TYPE_CHECKING`` 内の import 名が注釈に出ていない。"""
    root = Path(__file__).resolve().parent.parent
    violations = _collect_comken_violations(root)
    if not violations:
        return
    details = "\n".join(f"  {rel}:{line}: {name}" for rel, line, name in violations)
    fix = (
        "TYPE_CHECKING 内の import 名を型注釈に使っている箇所がある。"
        "通常の import にするか、ファイル先頭に "
        "``from __future__ import annotations`` を足してください。"
    )
    pytest.fail(f"{len(violations)} 件の違反:\n{details}\n\n{fix}")


# ── 検査ロジック自体のテスト ───────────────────────────────────────


_INSPECTION_CASES = [
    pytest.param(
        # (a) TYPE_CHECKING 名を引数注釈に使う → 引数と戻り値で同じ名前・同じ行なので
        # 1 件にまとまる
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from x import Y\n"
        "def f(arg: Y) -> Y: ...\n",
        1,
        id="type_checking_name_in_arg_annotation",
    ),
    pytest.param(
        # (b) 同じだが from __future__ あり → 違反なし
        "from __future__ import annotations\n"
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from x import Y\n"
        "def f(arg: Y) -> Y: ...\n",
        0,
        id="future_annotations_skips_file",
    ),
    pytest.param(
        # (c) 文字列注釈 → 違反なし
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from x import Y\n"
        "def f(arg: 'Y') -> 'Y': ...\n",
        0,
        id="string_annotations_ignored",
    ),
    pytest.param(
        # (d) 関数内ローカル変数の注釈のみ → 違反なし
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from x import Y\n"
        "def f() -> None:\n"
        "    local: Y = 1\n",
        0,
        id="local_annassign_inside_function_body_ignored",
    ),
    pytest.param(
        # (e) クラス本体の AnnAssign → 違反あり
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from x import Y\n"
        "class C:\n"
        "    attr: Y = 1\n",
        1,
        id="class_body_annassign_flagged",
    ),
    pytest.param(
        # (f) if ブロックの中で def した関数の引数注釈 → 違反あり
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from x import Y\n"
        "if True:\n"
        "    def f(arg: Y) -> None: ...\n",
        1,
        id="function_def_inside_if_flagged",
    ),
    pytest.param(
        # (g) try の中の class 本体の AnnAssign → 違反あり
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from x import Y\n"
        "try:\n"
        "    class C:\n"
        "        attr: Y = 1\n"
        "except Exception:\n"
        "    pass\n",
        1,
        id="class_inside_try_flagged",
    ),
    pytest.param(
        # (h) 関数の中で定義した class の本体の AnnAssign → 違反あり
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from x import Y\n"
        "def f() -> None:\n"
        "    class C:\n"
        "        attr: Y = 1\n",
        1,
        id="class_inside_function_body_flagged",
    ),
    pytest.param(
        # (i) 関数の中で定義したネスト関数の引数注釈 → 違反あり
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from x import Y\n"
        "def outer() -> None:\n"
        "    def inner(arg: Y) -> None: ...\n",
        1,
        id="nested_function_def_arg_flagged",
    ),
]


@pytest.mark.parametrize("source, expected", _INSPECTION_CASES)
def test_inspection_logic(source: str, expected: int) -> None:
    """ヘルパー関数 ``_collect_violations`` のロジック単体を小さなソースで確認する。

    各ケースが (a)〜(i) の想定どおりになるかを ``pytest.param(..., id=...)`` で表している。
    """
    tree = ast.parse(source)
    assert len(_collect_violations(tree)) == expected
