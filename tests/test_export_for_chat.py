"""export_for_chat.py のテスト。"""

import ast
import subprocess
import sys

import export_for_chat


def test_api_text_contains_csv_docstring() -> None:
    api_text = export_for_chat._api_text()

    assert "class CSV:" in api_text
    assert "columns: list[str] | None=None" in api_text
    assert "def append(" in api_text


def test_find_definition_follows_nested_reexport() -> None:
    package_file = export_for_chat.PACKAGE_ROOT / "core" / "files" / "__init__.py"

    definition = export_for_chat._find_definition(package_file, "DateNameBuilder")

    assert definition is not None
    _, node = definition
    assert isinstance(node, ast.ClassDef)
    assert node.name == "DateNameBuilder"


def test_split_preserves_text() -> None:
    text = "1行目\n2行目\n3行目\n"

    chunks = export_for_chat._split(text, max_chars=5)

    assert "".join(chunks) == text
    assert len(chunks) == 3


def test_script_can_import_comken_when_run_directly() -> None:
    result = subprocess.run(
        [sys.executable, "tools/export_for_chat.py", "--help"],
        cwd=export_for_chat.ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stderr
