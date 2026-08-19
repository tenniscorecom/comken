"""delete_files() のテスト。

複数ファイルをまとめて削除する関数。1件目で失敗しても残りは削除すること、
失敗分は ``FileDeletionError.remaining`` で取得できること、dry-run では
何も消さないことを確認する。
"""

from pathlib import Path

import pytest

from comken.core.files import delete_files
from comken.exceptions import FileDeletionError
from comken.runtime import dry_run


class TestDeleteFiles:
    """delete_files() の正常系 / 異常系 / dry-run。"""

    def test_deletes_all_files(self, tmp_path: Path) -> None:
        """全ファイルを削除できること。"""
        paths = [tmp_path / "a.txt", tmp_path / "b.txt", tmp_path / "c.txt"]
        for p in paths:
            p.write_text("data", encoding="utf-8")

        delete_files(paths)

        for p in paths:
            assert not p.exists()

    def test_returns_none_on_success(self, tmp_path: Path) -> None:
        """全件成功時は None を返す（戻り値は使わないが、明示）。"""
        path = tmp_path / "a.txt"
        path.write_text("data", encoding="utf-8")

        assert delete_files([path]) is None

    def test_continues_on_failure_and_reports_remaining(self, tmp_path: Path, monkeypatch) -> None:
        """1件失敗しても残り2件は消え、失敗分のみ remaining に残ること。"""
        path_a = tmp_path / "a.txt"
        path_b = tmp_path / "b.txt"
        path_c = tmp_path / "c.txt"
        for p in (path_a, path_b, path_c):
            p.write_text("data", encoding="utf-8")

        real_unlink = Path.unlink

        def fake_unlink(self, *args, **kwargs):
            if str(self) == str(path_b):
                raise OSError("permission denied")
            return real_unlink(self, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", fake_unlink)

        with pytest.raises(FileDeletionError) as excinfo:
            delete_files([path_a, path_b, path_c])

        assert excinfo.value.remaining == [path_b]
        assert not path_a.exists()
        assert not path_c.exists()
        # メッセージに残ったファイルのパスが並ぶこと
        assert str(path_b) in str(excinfo.value)

    def test_continues_on_failure_in_missing_ok_default(self, tmp_path: Path, monkeypatch) -> None:
        """missing_ok=True（既定）で OSError以外（TypeError等）はそのまま伝播する。

        認可・ファイル状態由来以外の例外（コードのバグ等）まで握り潰さないため。
        """
        path_a = tmp_path / "a.txt"
        path_b = tmp_path / "b.txt"
        for p in (path_a, path_b):
            p.write_text("data", encoding="utf-8")

        def fake_unlink(self, *args, **kwargs):
            raise TypeError("not an OS error")

        monkeypatch.setattr(Path, "unlink", fake_unlink)

        with pytest.raises(TypeError):
            delete_files([path_a, path_b])

    def test_dry_run_does_not_delete(self, tmp_path: Path) -> None:
        """dry-run ではファイルを消さず、warn ログだけ出す。"""
        path = tmp_path / "a.txt"
        path.write_text("data", encoding="utf-8")

        with dry_run():
            delete_files([path])

        assert path.exists()

    def test_missing_ok_handles_missing(self, tmp_path: Path) -> None:
        """missing_ok=True（既定）なら対象が存在しなくてもエラーにならない。"""
        path = tmp_path / "missing.txt"  # 存在しない

        assert delete_files([path]) is None

    def test_missing_ok_false_raises(self, tmp_path: Path) -> None:
        """missing_ok=False なら存在しないファイルで FileNotFoundError が出る。

        これは FileDeletionError ではない（delete_file() 内の普通の FileNotFoundError）。
        「無くてよい」が前提の場面では驚かないため、久しぶりに必要になったら、
        呼び出し側で missing_ok=False にして失敗できるようにしてある。
        """
        path = tmp_path / "missing.txt"

        with pytest.raises(FileNotFoundError):
            delete_files([path], missing_ok=False)
