"""comken の層をまたぐ import の向きを守るテスト。

目的は依存関係を完全に固定することではなく、**明らかな逆方向の依存を防ぐ**こと。

    直下（exceptions / runtime）→ core → toolbox → services

上の層から下の層への import は自由。下の層から上の層への import は禁止する。
同じ層の別コンポーネント同士（例: toolbox.excel → toolbox.windows）は、必要なものだけ
`ALLOWED_SAME_LAYER` に書く。増やす前に「その依存は本当に必要か」を先に考える。
"""

import ast
from pathlib import Path

LAYERS = {
    "exceptions": 0,
    "runtime": 0,
    "core": 1,
    "toolbox": 2,
    "services": 4,
}

# 同じ層の別コンポーネント同士で、実際に必要な依存。ここへ足して済ませず、まず設計を見直す。
ALLOWED_SAME_LAYER = {
    ("toolbox.excel", "toolbox.windows"),  # 既存数式・マクロ時の COM フォールバック
    ("toolbox.salesforce", "toolbox.credentials"),  # Salesforce の認証情報を安全に保存する
    ("toolbox.salesforce", "toolbox.csv"),  # レポート・SOQL・Data Loader の結果を CSV/Table にする
    ("toolbox.browser", "toolbox.salesforce"),  # レポートAPIの2000行上限をブラウザ経由で回避する
    ("toolbox.browser", "toolbox.credentials"),  # DPAPIに保存したID/パスワードでログインする
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


def _is_skippable(path: Path) -> bool:
    """層ルールの検査対象から外すファイルか。

    - `__main__.py` / `cli.py` は CLI 入口で、ライブラリとして import される層ではない
    - `run.py` は RPA スクリプトが直接呼び出す入口（`backoffice` / `intranet`）
    - `templates/` は配布される雛形で、comken パッケージの一部ではない
    """
    if path.name in ("__main__.py", "cli.py", "run.py"):
        return True
    return "templates" in path.parts


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


def _violations_in(path: Path) -> list[str]:
    """ファイル1つ分の import を調べて、禁止された依存の説明を返す。"""
    module = _module_name(path)
    source = _component(module)
    if source is None or source.split(".")[0] not in LAYERS:
        return []  # 層に属さないもの（comken/tools/ など）は対象外
    source_layer = LAYERS[source.split(".")[0]]
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        for imported in _resolve_import(module, node, is_package=path.name == "__init__.py"):
            target = _component(imported)
            if target is None or target == source or target.split(".")[0] not in LAYERS:
                continue
            target_layer = LAYERS[target.split(".")[0]]
            if target_layer < source_layer or (source, target) in ALLOWED_SAME_LAYER:
                continue
            found.append(
                f"{path.relative_to(REPOSITORY_ROOT)}:{node.lineno}: 禁止された依存 "
                f"{source} → {target}。下の層だけを import するか、設計を見直してください。"
            )
    return found


def test_imports_follow_layer_direction() -> None:
    """下の層から上の層への import と、許可されていない同層 import を禁止する。"""
    violations = [
        message
        for path in PACKAGE_ROOT.rglob("*.py")
        if not _is_skippable(path)
        for message in _violations_in(path)
    ]
    assert not violations, "\n" + "\n".join(violations)


# CSV の読み書きは comken.toolbox.csv.CSV に集約する。標準の csv を直接 import してよいのは、
# CSV クラス自身（toolbox/csv/）と toolbox を使えない core 層だけ。
CSV_DIRECT_IMPORT_ALLOWED = (
    PACKAGE_ROOT / "toolbox" / "csv",
    PACKAGE_ROOT / "core",
)


def _is_csv_import_allowed(path: Path) -> bool:
    return any(path == allowed or allowed in path.parents for allowed in CSV_DIRECT_IMPORT_ALLOWED)


def test_no_direct_csv_import_outside_allowed_places() -> None:
    """標準 csv を直接 import できるのは、許可された場所だけ。"""
    violations: list[str] = []
    for root in (PACKAGE_ROOT, REPOSITORY_ROOT / "tools"):
        for path in root.rglob("*.py"):
            if _is_skippable(path) or _is_csv_import_allowed(path):
                continue
            if _imports_stdlib_csv(path):
                violations.append(
                    f"{path.relative_to(REPOSITORY_ROOT)}: 標準の csv を直接 import しています。"
                    "CSV の読み書きは comken.toolbox.csv.CSV を使うこと。"
                )
    assert not violations, "\n" + "\n".join(violations)


def _imports_stdlib_csv(path: Path) -> bool:
    """ファイルが標準ライブラリの csv を import しているか（AST で判定）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == "csv" or alias.name.startswith("csv.") for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "csv" or module.startswith("csv."):
                return True
    return False
