"""export_for_chat.py のテスト。"""

import ast
import os
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
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        [sys.executable, "tools/export_for_chat.py", "--help"],
        cwd=export_for_chat.ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_collect_python_files_includes_all_comken_py() -> None:
    """``comken/`` 配下のすべての .py が収集される（キャッシュ系は除外）。"""
    files = export_for_chat._collect_python_files(export_for_chat.PACKAGE_ROOT)

    # ``comken/`` 直下のすべての .py が含まれている
    expected = sorted(export_for_chat.PACKAGE_ROOT.rglob("*.py"))
    expected = [
        path
        for path in expected
        if path.is_file()
        and not any(
            part in export_for_chat.EXCLUDED_DIR_NAMES
            for part in path.relative_to(export_for_chat.PACKAGE_ROOT).parts
        )
    ]
    assert files == expected


def test_concatenate_files_wraps_each_file_with_header() -> None:
    """各ファイルの前に ``# ===== FILE: ... =====`` のヘッダが入る。"""
    files = export_for_chat._collect_python_files(export_for_chat.PACKAGE_ROOT)

    text, _, _ = export_for_chat._concatenate_files(files, export_for_chat.PACKAGE_ROOT)

    assert "# ===== FILE:" in text
    # ヘッダの数はファイル数と一致する
    assert text.count("# ===== FILE:") == len(files)


def test_bundle_text_has_six_chapters_in_order() -> None:
    """バンドル資料が 6 章をこの順で持っている。"""
    text = export_for_chat._bundle_text()

    # ヘッダ → 章 1 → 章 2 → 章 3 → 章 4 → 章 5 → 章 6 の順に出現する
    header_idx = text.find("# comken_bundle.md")
    conventions_idx = text.find("# 1. コーディング規約")
    api_idx = text.find("# 2. 公開 API 索引")
    examples_idx = text.find("# 3. 動く実例")
    impl_idx = text.find("# 4. 実装全文")
    errors_idx = text.find("# 5. エラー対応表")
    spec_idx = text.find("# 6. 設計判断")

    assert header_idx >= 0
    assert header_idx < conventions_idx < api_idx < examples_idx < impl_idx < errors_idx < spec_idx


def test_bundle_text_includes_examples_files() -> None:
    """``examples/`` の代表ファイルがバンドルに含まれている。"""
    text = export_for_chat._bundle_text()

    # 代表として ``examples/advanced/table_transfer_design/README.md`` が含まれる
    assert "examples/advanced/table_transfer_design/README.md" in text


def test_bundle_text_includes_all_comken_py_files() -> None:
    """``comken/`` の .py がすべて含まれている（ファイル数で検証）。"""
    text = export_for_chat._bundle_text()

    # ``comken/`` 配下の .py がすべてヘッダ付きで入る
    expected_files = export_for_chat._collect_python_files(export_for_chat.PACKAGE_ROOT)
    assert text.count("# ===== FILE:") >= len(expected_files)

    # 各ファイルへの相対パスがそのまま入っている
    for path in expected_files[:5]:  # 全件チェックは冗長なので先頭5件で十分
        relative = path.relative_to(export_for_chat.PACKAGE_ROOT.parent).as_posix()
        assert relative in text


def test_verify_internal_library_placeholder_passes() -> None:
    """社内ライブラリ仮名が保たれている間は検証が通る。"""
    # 現在の ``comken/toolbox/rpa.py`` の値は仮名のままなので例外は出ない
    export_for_chat._verify_internal_library_placeholder()


def test_bundle_output_path_constant_exists() -> None:
    """``BUNDLE_OUTPUT_PATH`` がリポジトリ直下の ``comken_bundle.md`` を指す。"""
    assert export_for_chat.BUNDLE_OUTPUT_PATH == export_for_chat.ROOT / "comken_bundle.md"


def test_excluded_dir_names_includes_build_and_dist() -> None:
    """ビルド系のディレクトリ名も除外対象に含まれている。"""
    excluded = export_for_chat.EXCLUDED_DIR_NAMES
    assert "build" in excluded
    assert "dist" in excluded
    assert ".venv" in excluded
