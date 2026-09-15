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


def test_bundle_sections_are_in_order_with_implementation_split_by_package() -> None:
    """バンドル資料が章（カテゴリ）ごとに分かれ、実装全文はパッケージ単位でさらに分かれている。"""
    titles = [title for title, _ in export_for_chat._bundle_sections()]

    # 0 読み方 → 1 規約 → 2 API索引 → 3 実例 → 4 実装_* (複数) → 5 エラー表 → 6 設計判断 の順
    assert titles[0] == "0_読み方"
    assert titles[1] == "1_コーディング規約"
    assert titles[2] == "2_公開API索引"
    assert titles[3] == "3_動く実例"
    impl_titles = [title for title in titles if title.startswith("4_実装_")]
    assert impl_titles  # comken/ のパッケージ数だけ分かれている
    assert "4_実装_core" in impl_titles
    assert "4_実装_toolbox" in impl_titles
    assert titles[-2] == "5_エラー対応表"
    assert titles[-1] == "6_設計判断"


def test_bundle_sections_include_examples_files() -> None:
    """``examples/`` の代表ファイルが「3_動く実例」章に含まれている。"""
    sections = dict(export_for_chat._bundle_sections())

    assert "examples/advanced/table_transfer_design/README.md" in sections["3_動く実例"]


def test_bundle_sections_include_all_comken_py_files() -> None:
    """``comken/`` の .py がすべて、いずれかの「4_実装_*」章に含まれている。"""
    sections = export_for_chat._bundle_sections()
    implementation_text = "".join(text for title, text in sections if title.startswith("4_実装_"))

    expected_files = export_for_chat._collect_python_files(export_for_chat.PACKAGE_ROOT)
    assert implementation_text.count("# ===== FILE:") == len(expected_files)

    # 各ファイルへの相対パスがそのまま入っている
    for path in expected_files[:5]:  # 全件チェックは冗長なので先頭5件で十分
        relative = path.relative_to(export_for_chat.PACKAGE_ROOT.parent).as_posix()
        assert relative in implementation_text


def test_bundle_output_dir_constant_exists() -> None:
    """``BUNDLE_OUTPUT_DIR`` がリポジトリ直下の ``comken_bundle/`` を指す。"""
    assert export_for_chat.BUNDLE_OUTPUT_DIR == export_for_chat.ROOT / "comken_bundle"


def test_excluded_dir_names_includes_build_and_dist() -> None:
    """ビルド系のディレクトリ名も除外対象に含まれている。"""
    excluded = export_for_chat.EXCLUDED_DIR_NAMES
    assert "build" in excluded
    assert "dist" in excluded
    assert ".venv" in excluded
