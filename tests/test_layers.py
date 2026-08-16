"""comken の層をまたぐ import の向きを固定するテスト。"""

import ast
from pathlib import Path

LAYERS = {
    "exceptions": 0,
    "constants": 0,
    "runtime": 0,
    "deprecation": 0,
    "core": 1,
    "toolbox": 2,
    "services": 3,
}

ALLOWED_SAME_LAYER = {
    ("toolbox.excel", "toolbox.windows"),  # 既存数式・マクロ時の COM フォールバック
    ("toolbox.master_table", "toolbox.excel"),  # 管理表は Excel の表を読む
    ("toolbox.salesforce", "toolbox.credentials"),  # Salesforce の認証情報を安全に保存する
}

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPOSITORY_ROOT / "comken"


def _module_name(path: Path) -> str:
    relative = path.relative_to(REPOSITORY_ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _component(module: str) -> str | None:
    parts = module.split(".")
    if not parts or parts[0] != "comken" or len(parts) < 2:
        return None
    if parts[1] == "toolbox" and len(parts) >= 3:
        return ".".join(parts[1:3])
    return parts[1]


def _resolve_import(
    module: str, node: ast.Import | ast.ImportFrom, *, is_package: bool
) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if node.level == 0:
        return [node.module] if node.module else []
    package_parts = module.split(".") if is_package else module.split(".")[:-1]
    base_parts = package_parts[: len(package_parts) - node.level + 1]
    if node.module:
        base_parts.extend(node.module.split("."))
    base = ".".join(base_parts)
    return [base] if base else []


def test_imports_follow_layer_direction() -> None:
    """上向き import と未承認の同層 import を禁止する。"""
    found_same_layer: set[tuple[str, str]] = set()
    violations: list[str] = []

    for path in PACKAGE_ROOT.rglob("*.py"):
        module = _module_name(path)
        source = _component(module)
        if source is None:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for imported_module in _resolve_import(
                module, node, is_package=path.name == "__init__.py"
            ):
                target = _component(imported_module)
                if target is None or target == source:
                    continue
                edge = (source, target)
                source_layer = LAYERS[source.split(".")[0]]
                target_layer = LAYERS[target.split(".")[0]]
                if source_layer == target_layer and edge in ALLOWED_SAME_LAYER:
                    found_same_layer.add(edge)
                    continue
                if target_layer >= source_layer:
                    relative_path = path.relative_to(REPOSITORY_ROOT)
                    violations.append(
                        f"{relative_path}:{node.lineno}: 禁止された依存 {source} → {target}。"
                        "下の層だけを import するか、設計を見直してください。"
                    )

    unused = ALLOWED_SAME_LAYER - found_same_layer
    for source, target in sorted(unused):
        violations.append(
            f"許可一覧の依存 {source} → {target} は実際には存在しません。"
            "不要になった行を ALLOWED_SAME_LAYER から削除してください。"
        )

    assert not violations, "\n" + "\n".join(violations)
