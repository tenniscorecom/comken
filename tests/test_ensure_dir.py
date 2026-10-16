"""comken.core.files.ensure_dir のテスト。

``path.mkdir(parents=True, exist_ok=True)`` を 1 か所に置き換えた版。
確認点は次のとおり。

- 通常: フォルダを作って ``Path`` を返す
- 既にあるフォルダ: 例外を出さず ``Path`` を返す
- dry-run 中: フォルダを作らず ``[DRY-RUN]`` ログを出して ``Path`` を返す
- dry-run 中に nested path を渡しても親を作らない
- 戻り値は str / Path どちらでも ``Path`` で返る
- dry-run 後に状態を漏らさない
"""

import logging

from comken.core.files import ensure_dir
from comken.runtime import is_dry_run


class TestCreateDir:
    def test_creates_missing_directory(self, tmp_path) -> None:
        """存在しないフォルダを作って Path を返す。"""
        target = tmp_path / "new" / "nested"
        assert not target.exists()

        result = ensure_dir(target)

        assert target.is_dir()
        assert result == target

    def test_no_error_on_existing_directory(self, tmp_path) -> None:
        """既にあるフォルダを渡しても例外を出さない。"""
        target = tmp_path / "already"
        target.mkdir()

        result = ensure_dir(target)

        assert target.is_dir()
        assert result == target

    def test_accepts_str_path(self, tmp_path) -> None:
        """str を渡しても Path に直して返す。"""
        target = tmp_path / "from_str"
        result = ensure_dir(str(target))

        assert result == target
        assert target.is_dir()

    def test_creates_parents(self, tmp_path) -> None:
        """parents=True 相当なので、間の階層のフォルダもまとめて作る。"""
        target = tmp_path / "a" / "b" / "c"
        assert not target.parent.exists()

        result = ensure_dir(target)

        assert result == target
        assert target.is_dir()
        assert (tmp_path / "a").is_dir()
        assert (tmp_path / "a" / "b").is_dir()


class TestDryRun:
    def test_does_not_create_directory_under_dry_run(self, tmp_path, caplog) -> None:
        """dry-run 中はフォルダを作らず、ログだけ出して Path を返す。"""
        target = tmp_path / "skip_me"
        assert not target.exists()

        with caplog.at_level(logging.INFO):
            from comken import dry_run as comken_dry_run

            with comken_dry_run():
                result = ensure_dir(target)

        assert not target.exists()  # 実際には作られていない
        assert result == target
        assert "[DRY-RUN]" in caplog.text

    def test_does_not_create_parents_under_dry_run(self, tmp_path, caplog) -> None:
        """dry-run 中に nested パスを渡しても親ディレクトリも作らない。"""
        target = tmp_path / "x" / "y" / "z"
        assert not (tmp_path / "x").exists()

        with caplog.at_level(logging.INFO):
            from comken import dry_run as comken_dry_run

            with comken_dry_run():
                result = ensure_dir(target)

        assert result == target
        assert not (tmp_path / "x").exists()  # 親も作らない
        assert "[DRY-RUN]" in caplog.text

    def test_state_does_not_leak_after_dry_run(self, tmp_path) -> None:
        """dry-run を抜けたら状態は元に戻る。"""
        target = tmp_path / "check"
        from comken import dry_run as comken_dry_run

        assert is_dry_run() is False
        with comken_dry_run():
            ensure_dir(target)
        assert is_dry_run() is False
        # dry-run 中は作られていない
        assert not target.exists()
        # dry-run 外で呼ぶと作られる
        ensure_dir(target)
        assert target.is_dir()
