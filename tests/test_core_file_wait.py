"""``comken.core.files.wait`` のテスト。

ファイル出現待ちの挙動を検証する。
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from comken.core.files.wait import wait_for_file


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

    def test_from_comken_core_files(self) -> None:
        """``comken.core.files`` からも取得できる。"""
        from comken.core.files import wait_for_file as direct

        assert direct is wait_for_file

    def test_does_not_leak_to_comken_top(self) -> None:
        """comken 直下には漏らさない（facade 拡張方針に従う）。"""
        import comken

        assert "wait_for_file" not in comken.__all__
        assert not hasattr(comken, "wait_for_file")
