"""``comken.core.wait`` の ``wait_for_file`` テスト。

ファイル出現待ちの挙動を検証する (Phase 4 で ``core.files.wait`` として
追加されたが、``core.wait`` に統合された)。
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from comken.core.wait import wait_for_file


class TestWaitForFile:
    def test_finds_existing_file(self, tmp_path: Path) -> None:
        """既に存在するファイルを即座に見つけて返す。"""
        target = tmp_path / "data_20260819.csv"
        target.write_text("header\n", encoding="utf-8")

        result = wait_for_file(tmp_path, "data_*.csv", timeout=5.0, poll_interval=0.1)

        assert result == target
        assert result.exists()

    def test_finds_with_literal_name(self, tmp_path: Path) -> None:
        """``*`` なしの固定名でも見つかる。"""
        target = tmp_path / "report.csv"
        target.write_text("x", encoding="utf-8")

        result = wait_for_file(tmp_path, "report.csv", timeout=5.0, poll_interval=0.1)

        assert result == target

    def test_raises_file_not_found_after_timeout(self, tmp_path: Path) -> None:
        """タイムアウト内にファイルが見つからなければ ``FileNotFoundError``。"""
        # フォルダは存在するが、マッチするファイルが無い
        start = time.monotonic()
        with pytest.raises(FileNotFoundError) as exc_info:
            wait_for_file(
                tmp_path,
                "missing_*.csv",
                timeout=1.0,
                poll_interval=0.2,
            )
        elapsed = time.monotonic() - start

        # タイムアウト時間が経過している (sleep が1回以上走るので1秒±α)
        assert elapsed >= 0.9
        assert "missing_*.csv" in str(exc_info.value)

    def test_returns_latest_by_mtime(self, tmp_path: Path) -> None:
        """複数マッチしたときは mtime が最新のファイルを返す。"""
        old = tmp_path / "data_old.csv"
        new = tmp_path / "data_new.csv"
        old.write_text("old", encoding="utf-8")
        # mtime の差を確実にするため少し待つ
        time.sleep(0.05)
        new.write_text("new", encoding="utf-8")

        result = wait_for_file(tmp_path, "data_*.csv", timeout=5.0, poll_interval=0.1)

        assert result == new

    def test_waits_until_file_appears(self, tmp_path: Path) -> None:
        """最初はファイルが無いが、後から現れたのを拾える。"""
        target_name = "later.csv"

        def appear_later() -> None:
            time.sleep(0.3)
            (tmp_path / target_name).write_text("later", encoding="utf-8")

        thread = threading.Thread(target=appear_later)
        thread.start()
        try:
            result = wait_for_file(tmp_path, "*.csv", timeout=5.0, poll_interval=0.1)
        finally:
            thread.join()

        assert result.name == target_name

    def test_ignores_directories_matching_pattern(self, tmp_path: Path) -> None:
        """パターンに同名フォルダがあっても無視する (ファイルのみ)。"""
        # 同名のフォルダを作り、ファイルは作らない
        (tmp_path / "data_x.csv").mkdir()

        with pytest.raises(FileNotFoundError):
            wait_for_file(
                tmp_path,
                "data_*.csv",
                timeout=0.5,
                poll_interval=0.1,
            )

    def test_missing_folder_fails_immediately(self, tmp_path: Path) -> None:
        """フォルダが無いときは待たずに即座に失敗し、フォルダの不在だと分かる。

        「何を防いでいるか」: ``Path.glob()`` は存在しないフォルダでも例外を
        出さず空を返すので、区別しないと「共有サーバーが切れている」も
        「ファイルがまだ来ていない」と同じ形で timeout 後に失敗し、
        原因究明が遅れる。フォルダの不在は待っても直らない。
        """
        missing = tmp_path / "no_such_folder"

        start = time.monotonic()
        with pytest.raises(FileNotFoundError) as exc_info:
            wait_for_file(missing, "data_*.csv", timeout=5.0, poll_interval=0.1)
        elapsed = time.monotonic() - start

        # timeout を待たずに返る（待っていたら 5 秒かかる）
        assert elapsed < 1.0
        # 「ファイルが無い」ではなく「フォルダが無い」と言っている
        assert "フォルダ" in str(exc_info.value)
        assert "data_*.csv" not in str(exc_info.value)

    def test_file_given_as_folder_raises_not_a_directory(self, tmp_path: Path) -> None:
        """``folder`` にファイルを渡したら ``NotADirectoryError``。"""
        not_a_folder = tmp_path / "data.csv"
        not_a_folder.write_text("x", encoding="utf-8")

        with pytest.raises(NotADirectoryError):
            wait_for_file(not_a_folder, "*.csv", timeout=5.0, poll_interval=0.1)

    def test_timeout_message_points_at_the_file_not_the_folder(self, tmp_path: Path) -> None:
        """フォルダはあるのに来ない場合は、フォルダではなくファイルの話をする。

        フォルダ不在との言い分けができていることを、両方向から固定する。
        """
        with pytest.raises(FileNotFoundError) as exc_info:
            wait_for_file(tmp_path, "missing_*.csv", timeout=0.5, poll_interval=0.1)

        message = str(exc_info.value)
        assert "missing_*.csv" in message
        assert "監視するフォルダがありません" not in message

    def test_folder_disappearing_while_waiting_is_reported_as_missing_folder(
        self, tmp_path: Path
    ) -> None:
        """待っている間にフォルダが消えたら、ファイルではなくフォルダの不在を知らせる。

        共有サーバーが待機中に切れたケース。timeout まで待った末に
        「ファイルが来ない」と言われると、原因を取り違える。
        """
        watched = tmp_path / "input"
        watched.mkdir()

        def remove_later() -> None:
            time.sleep(0.2)
            watched.rmdir()

        thread = threading.Thread(target=remove_later)
        thread.start()
        try:
            with pytest.raises(FileNotFoundError) as exc_info:
                wait_for_file(watched, "data_*.csv", timeout=1.0, poll_interval=0.1)
        finally:
            thread.join()

        assert "監視するフォルダがありません" in str(exc_info.value)

    def test_accepts_string_path(self, tmp_path: Path) -> None:
        """``folder`` には str も受け付ける (Path に変換される)。"""
        target = tmp_path / "data.csv"
        target.write_text("x", encoding="utf-8")

        result = wait_for_file(str(tmp_path), "data.csv", timeout=5.0, poll_interval=0.1)

        assert result == target


class TestFacadeExports:
    def test_from_comken_core(self) -> None:
        """``comken.core`` から取得できる。"""
        import comken.core

        assert hasattr(comken.core, "wait_for_file")
        assert "wait_for_file" in comken.core.__all__
        assert callable(comken.core.wait_for_file)

    def test_does_not_leak_to_comken_top(self) -> None:
        """comken 直下には漏らさない（facade 拡張方針に従う）。"""
        import comken

        assert "wait_for_file" not in comken.__all__
        assert not hasattr(comken, "wait_for_file")
