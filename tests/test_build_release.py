"""tools/build_release.py のテスト。

小さな一時 git リポジトリで ``git archive`` の代わりをし、フォルダ生成 /
``RELEASE.txt`` 書き込み / タグと ``__version__`` の整合性検査 /
robocopy コマンド組み立てを検証する。

git が無い環境ではテスト全体を ``pytest.skip`` する（このツールは git が
ある開発 PC で動かすもの）。
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

import build_release
import pytest

# git が無い環境ではテスト全体を skip する（このツールは git のある開発 PC
# 専用なので、git の無い CI で無理に動かす意味は無い）
pytestmark = pytest.mark.skipif(
    shutil.which("git") is None,
    reason="git が無いためスキップ",
)


# ── フィクスチャ・ヘルパー ────────────────────────────────────────────────


def _git(repo: Path, *args: str) -> None:
    """git コマンドをテスト用設定で実行するヘルパー。

    ユーザー設定は ``-c`` で毎回指定し、テスト環境に依存させない。
    """
    env = os.environ.copy()
    env["LC_ALL"] = "C.UTF-8"
    env["GIT_TERMINAL_PROMPT"] = "0"
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=tester",
            "-c",
            "user.email=tester@example.com",
            *args,
        ],
        cwd=repo,
        check=True,
        env=env,
        capture_output=True,
    )


def _make_repo(parent: Path, *, version: str) -> Path:
    """``__version__ = <version>`` の小さな一時リポジトリを作って ``v<version>`` タグを打つ。"""
    repo = parent / "repo"
    repo.mkdir()
    (repo / "comken").mkdir()
    (repo / "comken" / "__init__.py").write_text(
        f'__version__ = "{version}"\n',
        encoding="utf-8",
    )
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _git(repo, "init", "--initial-branch=main")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    _git(repo, "tag", f"v{version}")
    return repo


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    """``__version__ = "1.2.3"``・タグ ``v1.2.3`` を持つ一時リポジトリ。"""
    return _make_repo(tmp_path, version="1.2.3")


# ── 正常系 ────────────────────────────────────────────────────────────────


class TestBuildReleaseSuccess:
    """タグと ``__version__`` が一致しているときの正常な生成。"""

    def test_creates_folder(
        self,
        sample_repo: Path,
        tmp_path: Path,
    ) -> None:
        """フォルダと ``RELEASE.txt`` が作られ、``__version__`` が一致する。"""
        dest = tmp_path / "out"
        artifacts = build_release.build_release(
            tag="v1.2.3",
            dest=dest,
            server_path=r"\\server\share\tools\comken",
            force=False,
            repo_root=sample_repo,
        )

        assert artifacts.folder == dest / "comken-v1.2.3"
        assert artifacts.folder.is_dir()

        # フォルダの中身
        init_text = (artifacts.folder / "comken" / "__init__.py").read_text(encoding="utf-8")
        assert init_text == '__version__ = "1.2.3"\n'
        readme_text = (artifacts.folder / "README.md").read_text(encoding="utf-8")
        assert readme_text == "hello\n"

        # RELEASE.txt にタグ・コミット・__version__ が書かれている
        release_text = (artifacts.folder / "RELEASE.txt").read_text(encoding="utf-8")
        assert "tag: v1.2.3" in release_text
        assert "__version__: 1.2.3" in release_text
        assert artifacts.commit in release_text


class TestUntrackedExcluded:
    """``git archive`` は未コミット・未追跡のファイルを含まないため、

    リリース用フォルダにも入らない。
    """

    def test_untracked_files_are_not_included(
        self,
        sample_repo: Path,
        tmp_path: Path,
    ) -> None:
        # コミット後に未追跡ファイルを置く
        (sample_repo / "secret.txt").write_text("nope", encoding="utf-8")
        # 既存ファイルの変更（未コミット）も入らないことを確認するため、
        # ``__init__.py`` を編集だけして保存
        init_path = sample_repo / "comken" / "__init__.py"
        modified_text = init_path.read_text(encoding="utf-8") + "# WIP\n"
        init_path.write_text(modified_text, encoding="utf-8")

        artifacts = build_release.build_release(
            tag="v1.2.3",
            dest=tmp_path / "out",
            server_path=r"\\server\share\tools\comken",
            force=False,
            repo_root=sample_repo,
        )

        assert not (artifacts.folder / "secret.txt").exists()
        # 未コミットの編集も反映されない（タグ時点のコミット内容のまま）
        init_in_artifact = (artifacts.folder / "comken" / "__init__.py").read_text(encoding="utf-8")
        assert init_in_artifact == '__version__ = "1.2.3"\n'


# ── エラー系 ───────────────────────────────────────────────────────────────


class TestVersionMismatch:
    """タグ時点の ``__version__`` がタグ番号と食い違ったらエラーで何も作らない。"""

    def test_raises_when_version_does_not_match(
        self,
        sample_repo: Path,
        tmp_path: Path,
    ) -> None:
        # 既存のコミット（__version__ = "1.2.3"）に ``v9.9.9`` タグを打つ。
        # タグ番号から計算した ``expected_version = "9.9.9"`` と
        # タグ時点の ``__version__ = "1.2.3"`` が食い違う状態にする
        _git(sample_repo, "tag", "v9.9.9")
        dest = tmp_path / "out"

        with pytest.raises(build_release.ReleaseBuildError, match="一致しません"):
            build_release.build_release(
                tag="v9.9.9",
                dest=dest,
                server_path=r"\\server\share\tools\comken",
                force=False,
                repo_root=sample_repo,
            )
        # 検査で止まるので、フォルダの中身は作られていない
        assert not (dest / "comken-v9.9.9").exists()


class TestTagNotFound:
    """存在しないタグを指定したらエラー。"""

    def test_raises_when_tag_missing(
        self,
        sample_repo: Path,
        tmp_path: Path,
    ) -> None:
        with pytest.raises(build_release.ReleaseBuildError, match="見つかりません"):
            build_release.build_release(
                tag="v9.9.9",
                dest=tmp_path / "out",
                server_path=r"\\server\share\tools\comken",
                force=False,
                repo_root=sample_repo,
            )


# ── 既存出力の扱い ────────────────────────────────────────────────────────


class TestExistingDestination:
    """既存出力先の上書き制御と ``--force`` の安全性。"""

    def test_existing_dest_fails_without_force(
        self,
        sample_repo: Path,
        tmp_path: Path,
    ) -> None:
        dest = tmp_path / "out"
        build_release.build_release(
            tag="v1.2.3",
            dest=dest,
            server_path=r"\\server\share\tools\comken",
            force=False,
            repo_root=sample_repo,
        )
        with pytest.raises(build_release.ReleaseBuildError, match="既に存在します"):
            build_release.build_release(
                tag="v1.2.3",
                dest=dest,
                server_path=r"\\server\share\tools\comken",
                force=False,
                repo_root=sample_repo,
            )

    def test_force_rebuilds(
        self,
        sample_repo: Path,
        tmp_path: Path,
    ) -> None:
        dest = tmp_path / "out"
        build_release.build_release(
            tag="v1.2.3",
            dest=dest,
            server_path=r"\\server\share\tools\comken",
            force=False,
            repo_root=sample_repo,
        )
        # 2回目は ``--force`` で再生成できる
        artifacts = build_release.build_release(
            tag="v1.2.3",
            dest=dest,
            server_path=r"\\server\share\tools\comken",
            force=True,
            repo_root=sample_repo,
        )
        assert artifacts.folder.is_dir()

    def test_force_does_not_delete_outside_dest(
        self,
        sample_repo: Path,
        tmp_path: Path,
    ) -> None:
        """``force`` でも ``dest`` の外は消さない。"""
        other = tmp_path / "other"
        other.mkdir()
        other_file = other / "keep.txt"
        other_file.write_text("keep", encoding="utf-8")

        dest = tmp_path / "out"
        build_release.build_release(
            tag="v1.2.3",
            dest=dest,
            server_path=r"\\server\share\tools\comken",
            force=False,
            repo_root=sample_repo,
        )
        build_release.build_release(
            tag="v1.2.3",
            dest=dest,
            server_path=r"\\server\share\tools\comken",
            force=True,
            repo_root=sample_repo,
        )
        assert other_file.exists()


# ── robocopy コマンド ─────────────────────────────────────────────────────


class TestRobocopyCommand:
    """robocopy コマンドに除外3ファイルがすべて含まれ、``/MIR`` がある。"""

    def test_contains_all_excluded_files_and_mir(
        self,
        sample_repo: Path,
        tmp_path: Path,
    ) -> None:
        artifacts = build_release.build_release(
            tag="v1.2.3",
            dest=tmp_path / "out",
            server_path=r"\\server\share\tools\comken",
            force=False,
            repo_root=sample_repo,
        )

        command = artifacts.robocopy_command
        assert command.startswith("robocopy ")
        assert "/MIR" in command
        assert "/XF" in command

        # ``/XF`` は**送り元（配布用フォルダ）側**のフルパス（バックスラッシュ区切り、
        # 引用符付き）で並ぶ。
        # 宛先側のフルパスだと robocopy が一致と見なさず、共有サーバーの値が上書きされる
        source_dir = artifacts.folder
        for excluded in build_release.EXCLUDED_RELATIVE_PATHS:
            expected = '"' + str(source_dir) + "\\" + excluded.replace("/", "\\") + '"'
            assert expected in command, (
                f"robocopy コマンドから除外パスが消えている: {expected}\n実際のコマンド: {command}"
            )
            server_side = '"\\\\server\\share\\tools\\comken\\' + excluded.replace("/", "\\") + '"'
            assert server_side not in command, (
                "宛先側のフルパスで /XF を書いてはいけない（robocopy は送り元側で照合する）"
            )


# ── 既定タグ ──────────────────────────────────────────────────────────────


class TestDefaultTagFromVersion:
    """``comken/__init__.py`` の ``__version__`` から ``v<version>`` を作る。"""

    def test_reads_v_prefix(self, tmp_path: Path) -> None:
        (tmp_path / "comken").mkdir()
        (tmp_path / "comken" / "__init__.py").write_text(
            '__version__ = "4.5.6"\n',
            encoding="utf-8",
        )
        assert build_release.default_tag_from_version(tmp_path) == "v4.5.6"

    def test_raises_when_version_missing(self, tmp_path: Path) -> None:
        (tmp_path / "comken").mkdir()
        (tmp_path / "comken" / "__init__.py").write_text("# no version\n")
        with pytest.raises(build_release.ReleaseBuildError):
            build_release.default_tag_from_version(tmp_path)


# ── CLI 表示（warning ログとして出す） ───────────────────────────────────


class TestMainOutput:
    """``main()`` が robocopy コマンドと注意事項を ``logger.warning`` で出す。"""

    def test_main_emits_robocopy_command(
        self,
        sample_repo: Path,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        argv = [
            "--tag",
            "v1.2.3",
            "--dest",
            str(tmp_path / "out"),
            "--repo-root",
            str(sample_repo),
        ]
        with caplog.at_level(logging.WARNING):
            assert build_release.main(argv) == 0

        all_text = "\n".join(record.getMessage() for record in caplog.records)
        assert "robocopy " in all_text
        assert "/MIR" in all_text
        for excluded in build_release.EXCLUDED_RELATIVE_PATHS:
            assert excluded.replace("/", "\\") in all_text
