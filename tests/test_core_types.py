"""``comken.core.types``（共通の型の名前）のテスト。"""

import ast
from datetime import datetime
from pathlib import Path

from comken.core.types import Row, TypeMap, Value

_PACKAGE = Path(__file__).resolve().parent.parent / "comken"
_DEFINED_ONLY_IN_TYPES = ("Row", "Value", "TypeMap")


def test_value_accepts_cell_values_including_datetime() -> None:
    cells: dict[str, Value] = {
        "文字": "x",
        "整数": 1,
        "小数": 0.5,
        "真偽": True,
        "日時": datetime(2026, 10, 17),
    }

    assert len(cells) == 5


def test_row_and_type_map_are_plain_containers() -> None:
    row: Row = {"金額": "1000"}
    converters: TypeMap = {"金額": int}

    assert converters["金額"](row["金額"]) == 1000


def test_shared_types_are_defined_only_in_core_types() -> None:
    """``Row`` / ``Value`` / ``TypeMap`` を、他のモジュールで別々に定義し直さない。

    以前は ``Value`` が 3 か所で別々に定義され、内容もずれていた。
    """
    defined_elsewhere: list[str] = []
    for path in sorted(_PACKAGE.rglob("*.py")):
        if path.name == "types.py" and path.parent.name == "core":
            continue
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            names: list[str] = []
            if isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names = [node.target.id]
            elif isinstance(node, ast.TypeAlias):
                names = [node.name.id]
            defined_elsewhere += [
                f"{path.relative_to(_PACKAGE.parent)}: {name}"
                for name in names
                if name in _DEFINED_ONLY_IN_TYPES
            ]

    assert defined_elsewhere == []
