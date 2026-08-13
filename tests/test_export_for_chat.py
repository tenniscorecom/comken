"""export_for_chat.py のテスト。"""

import ast

import export_for_chat


def test_api_text_contains_full_csv_reader_docstring() -> None:
    api_text = export_for_chat._api_text()

    assert "class CsvReader(CsvBase):" in api_text
    assert "def __init__(self, path: str | Path" in api_text
    assert "encoding: str=Encoding.AUTO" in api_text
    assert "CP932（Shift-JIS）の順に自動判定する。" in api_text
    assert "CsvNoDataRowsError: データ行が1行もない場合。" in api_text


def test_find_definition_follows_nested_reexport() -> None:
    package_file = export_for_chat.PACKAGE_ROOT / "utils" / "files" / "__init__.py"

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
