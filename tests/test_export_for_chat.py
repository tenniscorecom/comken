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

    definition = export_for_chat._find_definition(package_file, "find_dated_file")

    assert definition is not None
    _, node = definition
    assert isinstance(node, ast.FunctionDef)
    assert node.name == "find_dated_file"


def test_split_preserves_text() -> None:
    text = "1行目\n2行目\n3行目\n"

    chunks = export_for_chat._split(text, max_bytes=5)

    assert "".join(chunks) == text
    assert len(chunks) == 3


def test_split_uses_utf8_byte_length_not_character_count() -> None:
    """日本語1文字は3バイトになるため、文字数ではなくバイト数で判定する。"""
    # "あ"（3バイト）を3個。1行あたり9バイトなので、max_bytes=10だと2行ごとには
    # 収まらない（9+9=18>10）が、文字数（3）で判定していれば2行分（6）は収まってしまう
    text = "あああ\n" * 4

    chunks = export_for_chat._split(text, max_bytes=10)

    assert "".join(chunks) == text
    assert len(chunks) == 4  # 1行（9バイト）ごとに分かれる


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


def test_bundle_sections_are_five_large_chapters_in_order() -> None:
    """バンドル資料は少数の大きな章にまとまっている（細分化しない）。"""
    titles = [title for title, _ in export_for_chat._bundle_sections()]

    assert titles == [
        "0_読み方",
        "1_規約_API索引_実例",
        "2_実装全文",
        "3_エラー対応表_設計判断",
        "4_新規プロジェクト向け",
    ]


def test_bundle_sections_have_no_duplicate_titles_or_content() -> None:
    """章ごとに1ファイルへ分けた後も、同じ内容が2箇所に重複して入らない。

    以前は貼り付け用/（旧方式）と comken_bundle/（新方式）が併存し、
    コーディング規約などが両方に丸ごと重複していた。廃止した今、
    タイトルの重複が無いことだけを確かめれば十分（内容はソースが1箇所しか無い）。
    """
    titles = [title for title, _ in export_for_chat._bundle_sections()]

    assert len(titles) == len(set(titles))


def test_bundle_sections_include_examples_files() -> None:
    """``examples/`` の代表ファイルが「1_規約_API索引_実例」章に含まれている。"""
    sections = dict(export_for_chat._bundle_sections())

    assert "examples/advanced/table_transfer_design/README.md" in sections["1_規約_API索引_実例"]


def test_bundle_sections_include_all_comken_py_files() -> None:
    """``comken/`` の .py がすべて「2_実装全文」章に含まれている。"""
    sections = dict(export_for_chat._bundle_sections())
    implementation_text = sections["2_実装全文"]

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


def test_section_4_contains_new_project_guide() -> None:
    """4章に作り方の文書（``docs/新規プロジェクトの作り方.md``）の本文がそのまま入る。

    見出し行（"# 新規プロジェクトの作り方（docs/新規プロジェクトの作り方.md）"）と、
    「2. AI が守ること」の節が含まれていることだけを確かめれば十分。
    """
    sections = dict(export_for_chat._bundle_sections())
    section_4 = sections["4_新規プロジェクト向け"]

    assert "# 新規プロジェクトの作り方（docs/新規プロジェクトの作り方.md）" in section_4
    assert "## 2. AI が守ること" in section_4


def test_section_4_contains_all_template_files() -> None:
    """4章に、ひな形の全ファイル（除外後）が ``# ===== FILE: ...`` 形式で入っている。"""
    sections = dict(export_for_chat._bundle_sections())
    section_4 = sections["4_新規プロジェクト向け"]

    import re

    # 除外後の実ファイル一覧（テスト側で再計算）とバンドル側のヘッダ件数が一致する。
    expected_files = export_for_chat._collect_template_files(export_for_chat.TEMPLATE_DIR)
    expected_headers = [
        f"# ===== FILE: {path.relative_to(export_for_chat.ROOT).as_posix()}"
        for path in expected_files
    ]
    for header in expected_headers:
        assert header in section_4, f"ヘッダが見つかりません: {header}"

    # 逆方向: バンドル側にあるヘッダはすべて実ファイルに対応している。
    actual_headers = re.findall(r"^# ===== FILE: (.+?) （", section_4, re.MULTILINE)
    assert len(actual_headers) == len(expected_files)
    assert set(actual_headers) == {
        path.relative_to(export_for_chat.ROOT).as_posix() for path in expected_files
    }


def test_section_4_keeps_bat_japanese_without_mojibake() -> None:
    """``実行.bat`` の中身（日本語コメント・``PYTHON_LIBRARY``）が文字化けせず、
    見出しに ``cp932`` が書かれている。
    """
    sections = dict(export_for_chat._bundle_sections())
    section_4 = sections["4_新規プロジェクト向け"]

    bat_header = "# ===== FILE: comken/templates/新規プロジェクト/実行.bat"
    assert bat_header in section_4
    # ヘッダに cp932 が書かれている（cp932 ファイルはそう判定される）
    assert "文字コード: cp932" in section_4
    # .bat は CRLF で保存させる。作業ツリーの改行は PC ごとに違うので、
    # 見出しには「必須の形」を書き、それ以外のファイルには改行コードを書かない
    assert "改行: CRLF で保存する" in section_4
    assert "改行: LF" not in section_4
    # 日本語のコメントが本文にそのまま入っている
    assert "このツールの起動用" in section_4
    # PYTHON_LIBRARY の値もそのまま
    assert "PYTHON_LIBRARY=\\\\server\\share\\tools" in section_4


def test_section_4_excludes_ruff_cache_and_pyc_and_real_config() -> None:
    """4章の ``# ===== FILE: ...`` ヘッダに、除外対象（``.ruff_cache`` /
    ``__pycache__`` / ``config.ini`` 本物）が現れない。

    ``.gitignore`` の本文に ``.ruff_cache/`` という文字列が現れるのは除外対象とは
    無関係なので、ヘッダ行だけを抜き出して判定する。
    """
    import re

    sections = dict(export_for_chat._bundle_sections())
    section_4 = sections["4_新規プロジェクト向け"]
    headers = re.findall(r"^# ===== FILE: (.+?) （", section_4, re.MULTILINE)

    for forbidden in (".ruff_cache", "__pycache__"):
        assert not any(forbidden in h for h in headers), (
            f"除外されるべき {forbidden} のヘッダが4章に含まれています"
        )
    # config.ini（本物）はテンプレートの config.ini.example とは別。example は残す。
    assert "comken/templates/新規プロジェクト/config.ini" not in headers
    # example は入っている
    assert "comken/templates/新規プロジェクト/config.ini.example" in headers


def test_readme_mentions_new_project_section_and_drops_old_phrase() -> None:
    """``0_読み方`` に「新規プロジェクト」の案内と ``docs/新規プロジェクトの作り方.md``
    への参照が入り、旧文言「comken を使うだけなら不要です」は消えている。
    """
    sections = dict(export_for_chat._bundle_sections())
    readme = sections["0_読み方"]

    assert "新規プロジェクト" in readme
    assert "docs/新規プロジェクトの作り方.md" in readme
    assert "comken を使うだけなら不要です" not in readme


def test_collect_template_files_matches_disk_and_excludes_expected() -> None:
    """``_collect_template_files`` は除外後の実ファイルだけを、
    相対パスの昇順（README.md 先頭）で返す。"""
    files = export_for_chat._collect_template_files(export_for_chat.TEMPLATE_DIR)
    rels = [p.relative_to(export_for_chat.ROOT).as_posix() for p in files]

    # README.md が先頭
    assert rels[0] == "comken/templates/新規プロジェクト/README.md"
    # 除外対象が含まれない（パス区切り単位）
    for forbidden in (".ruff_cache", "__pycache__"):
        assert not any(f"/{forbidden}/" in r or r.endswith(f"/{forbidden}") for r in rels)
    # config.ini（本物）は無く、config.ini.example はある
    assert "comken/templates/新規プロジェクト/config.ini" not in rels
    assert "comken/templates/新規プロジェクト/config.ini.example" in rels
    # 残りは相対パスの昇順
    rest = rels[1:]
    assert rest == sorted(rest)


def test_detect_encoding_and_text_handles_both_encodings() -> None:
    """UTF-8 と cp932 を読み分け、改行を ``\\n`` に正規化する。"""
    utf8_path = export_for_chat.TEMPLATE_DIR / "README.md"
    cp932_path = export_for_chat.TEMPLATE_DIR / "実行.bat"

    encoding, _, body = export_for_chat._detect_encoding_and_text(utf8_path)
    assert encoding == "utf-8"
    assert "\r\n" not in body

    encoding, _, body = export_for_chat._detect_encoding_and_text(cp932_path)
    assert encoding == "cp932"
    assert "\r\n" not in body
    # 日本語が読める（cp932 で読めていればOK）
    assert "このツールの起動用" in body
