"""
rename_package.py（パッケージ名の一括変更ツール）のテスト。

実リポジトリは触らず、tmp_path にミニリポジトリを作って検証する。
"""

import importlib.util
from pathlib import Path

import pytest

# ルート直下のスクリプトをモジュールとして読み込む
_spec = importlib.util.spec_from_file_location(
    "rename_package", Path(__file__).parent.parent / "rename_package.py"
)
rename_package_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rename_package_module)

rename_package = rename_package_module.rename_package
replace_in_file = rename_package_module.replace_in_file


@pytest.fixture
def mini_repo(tmp_path):
    """comken 相当のミニリポジトリを作る。"""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "comken"\nversion = "0.2.0"\n', encoding="utf-8"
    )
    pkg = tmp_path / "comken"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("from comken.config import Config\n", encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "# comken\n\nfrom comken.excel import ExcelWriter\n", encoding="utf-8"
    )
    # bat は cp932（社内実環境の再現）
    (tmp_path / "実行.bat").write_bytes(
        "set COMKEN_SHARE=\\\\server\\tools\\comken\nrem コムケンの起動\n".encode("cp932")
    )
    return tmp_path


class TestRenamePackage:
    def test_replaces_imports_and_folder(self, mini_repo):
        """import 文・pyproject・フォルダ名がまとめて変わることを確認する。"""
        rename_package("mylib", [], dry_run=False, root=mini_repo)

        assert (mini_repo / "mylib").is_dir()
        assert not (mini_repo / "comken").exists()
        assert 'name = "mylib"' in (mini_repo / "pyproject.toml").read_text(encoding="utf-8")
        assert "from mylib.config" in (mini_repo / "mylib" / "__init__.py").read_text(
            encoding="utf-8"
        )
        assert "from mylib.excel" in (mini_repo / "README.md").read_text(encoding="utf-8")

    def test_replaces_uppercase_env_var_in_cp932_bat(self, mini_repo):
        """cp932 の bat 内の大文字環境変数（COMKEN_SHARE）も壊さず置換されることを確認する。"""
        rename_package("mylib", [], dry_run=False, root=mini_repo)

        bat = (mini_repo / "実行.bat").read_bytes().decode("cp932")  # cp932 のまま
        assert "MYLIB_SHARE" in bat
        assert "mylib" in bat
        assert "コムケン" in bat  # 日本語が文字化けしていない

    def test_dry_run_changes_nothing(self, mini_repo):
        """--dry-run では何も書き換わらないことを確認する。"""
        before = (mini_repo / "README.md").read_text(encoding="utf-8")

        rename_package("mylib", [], dry_run=True, root=mini_repo)

        assert (mini_repo / "comken").is_dir()  # フォルダもそのまま
        assert (mini_repo / "README.md").read_text(encoding="utf-8") == before

    def test_invalid_name_rejected(self, mini_repo):
        """パッケージ名として無効な名前は拒否されることを確認する。"""
        with pytest.raises(SystemExit, match="無効"):
            rename_package("My-Lib", [], dry_run=False, root=mini_repo)

    def test_same_name_rejected(self, mini_repo):
        """現在と同じ名前は拒否されることを確認する。"""
        with pytest.raises(SystemExit, match="同じ"):
            rename_package("comken", [], dry_run=False, root=mini_repo)

    def test_extra_project_folder_also_replaced(self, mini_repo, tmp_path):
        """追加で渡したプロジェクトフォルダの import も置換されることを確認する。"""
        project = tmp_path / "my_project"
        project.mkdir()
        (project / "main.py").write_text("from comken.csv import CsvReader\n", encoding="utf-8")

        rename_package("mylib", [project], dry_run=False, root=mini_repo)

        assert "from mylib.csv" in (project / "main.py").read_text(encoding="utf-8")
