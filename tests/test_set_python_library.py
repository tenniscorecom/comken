"""comken の場所をまとめて書き換えるツールのテスト。

リポジトリのルートで python -m pytest tests/test_set_python_library.py -v
"""

import pytest
from set_python_library import main

OLD_ROOT = r"\\old\share\tools\comken"
NEW_ROOT = r"\\new\share\tools\comken"

BAT_TEMPLATE = """@echo off
setlocal
rem このツールの起動用。日本語のコメントが化けないことも確かめる。

set "PYTHON_LIBRARY={root}"
set "PYTHONPATH=%PYTHON_LIBRARY%;%PYTHONPATH%"

pushd "%~dp0"
python main.py
popd
endlocal
"""

SETTINGS_TEMPLATE = """{{
  // comken の場所を VS Code に教える。
  "python.analysis.extraPaths": ["{root}"],
  "ruff.enable": true
}}
"""


def _project(parent, name, root=OLD_ROOT):
    """実行.bat と 認証情報の登録.bat と .vscode/settings.json を持つプロジェクトを1つ作る。"""
    folder = parent / name
    (folder / ".vscode").mkdir(parents=True)
    (folder / "実行.bat").write_text(BAT_TEMPLATE.format(root=root), encoding="cp932")
    (folder / "認証情報の登録.bat").write_text(BAT_TEMPLATE.format(root=root), encoding="cp932")
    (folder / ".vscode" / "settings.json").write_text(
        SETTINGS_TEMPLATE.format(root=root.replace("\\", "/")), encoding="utf-8"
    )
    return folder


def _bat_text(folder):
    return (folder / "認証情報の登録.bat").read_text(encoding="cp932")


def _run_bat_text(folder):
    return (folder / "実行.bat").read_text(encoding="cp932")


def _settings_text(folder):
    return (folder / ".vscode" / "settings.json").read_text(encoding="utf-8")


class TestApply:
    """--apply を付けたときの書き換え。"""

    def test_bat_points_to_the_new_place(self, tmp_path):
        folder = _project(tmp_path, "案件A")
        assert main([NEW_ROOT, str(folder), "--apply"]) == 0
        assert f'set "PYTHON_LIBRARY={NEW_ROOT}"' in _bat_text(folder)
        assert OLD_ROOT not in _bat_text(folder)

    def test_settings_json_uses_forward_slashes(self, tmp_path):
        """JSON では \\ が特殊文字なので / 区切りで書く。"""
        folder = _project(tmp_path, "案件A")
        main([NEW_ROOT, str(folder), "--apply"])
        assert '["//new/share/tools/comken"]' in _settings_text(folder)

    def test_japanese_comments_survive(self, tmp_path):
        """bat は CP932 のまま書き戻す（日本語のコメントが化けない）。"""
        folder = _project(tmp_path, "案件A")
        main([NEW_ROOT, str(folder), "--apply"])
        assert "日本語のコメントが化けない" in _bat_text(folder)
        assert (folder / "認証情報の登録.bat").read_bytes().decode("cp932")  # CP932 として読める

    def test_all_projects_under_the_folder(self, tmp_path):
        """プロジェクトを並べた親フォルダを渡すと、その下を全部書き換える。"""
        first = _project(tmp_path, "案件A")
        second = _project(tmp_path, "案件B")

        assert main([NEW_ROOT, str(tmp_path), "--apply"]) == 0

        assert NEW_ROOT in _bat_text(first)
        assert NEW_ROOT in _bat_text(second)

    def test_other_paths_are_not_touched(self, tmp_path):
        """extraPaths に comken 以外が入っていても巻き込まない。"""
        folder = _project(tmp_path, "案件A")
        settings = folder / ".vscode" / "settings.json"
        settings.write_text(
            '{\n  "python.analysis.extraPaths": ["//old/share/tools/comken", "./src"]\n}\n',
            encoding="utf-8",
        )

        main([NEW_ROOT, str(folder), "--apply"])

        text = _settings_text(folder)
        assert "//new/share/tools/comken" in text
        assert "./src" in text


class TestConfirmOnly:
    """--apply を付けないときは書き換えない。"""

    def test_nothing_is_written(self, tmp_path):
        folder = _project(tmp_path, "案件A")
        assert main([NEW_ROOT, str(folder)]) == 0
        assert OLD_ROOT in _bat_text(folder)

    def test_shows_old_and_new(self, tmp_path, capsys):
        """今どこを指していて、どこへ変わるかを見せる。"""
        folder = _project(tmp_path, "案件A")
        main([NEW_ROOT, str(folder)])

        out = capsys.readouterr().out
        assert OLD_ROOT in out
        assert NEW_ROOT in out
        assert "--apply" in out


class TestNothingToChange:
    """書き換えるものが無いとき。"""

    def test_already_pointing_there(self, tmp_path, capsys):
        """すでに新しい場所を指していれば対象にしない（何度実行してもよい）。"""
        folder = _project(tmp_path, "案件A", root=NEW_ROOT)
        assert main([NEW_ROOT, str(folder)]) == 1
        assert "見つかりませんでした" in capsys.readouterr().out

    def test_folder_without_projects(self, tmp_path):
        assert main([NEW_ROOT, str(tmp_path / "空")]) == 1


class TestArguments:
    def test_root_is_required(self):
        with pytest.raises(SystemExit):
            main([])
