"""単体実行向けログ設定のテスト。"""

import logging
from datetime import date

import pytest

from comken.core.logger import setup_logging


@pytest.fixture
def isolated_root_logger():
    """root logger の設定を退避し、テスト後に元へ戻す。"""
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    original_level = root_logger.level
    root_logger.handlers.clear()
    try:
        yield root_logger
    finally:
        added_handlers = [
            handler for handler in root_logger.handlers if handler not in original_handlers
        ]
        root_logger.handlers.clear()
        for handler in added_handlers:
            handler.close()
        root_logger.handlers.extend(original_handlers)
        root_logger.setLevel(original_level)


class TestSetupLogging:
    def test_adds_console_and_file_handlers(self, isolated_root_logger, tmp_path, monkeypatch):
        """コンソールとファイルの両方へ出力するハンドラを追加する。"""
        isolated_root_logger.handlers.clear()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("comken.core.logger.today", lambda: date(2026, 8, 13))

        setup_logging()

        assert len(isolated_root_logger.handlers) == 2
        assert any(
            type(handler) is logging.StreamHandler for handler in isolated_root_logger.handlers
        )
        assert any(
            isinstance(handler, logging.FileHandler) for handler in isolated_root_logger.handlers
        )
        assert (tmp_path / "logs" / "2026-08-13.log").exists()

    def test_preserves_existing_configuration(self, isolated_root_logger):
        """設定済みの場合はハンドラとレベルを変更しない。"""
        isolated_root_logger.handlers.clear()
        existing_handler = logging.StreamHandler()
        isolated_root_logger.addHandler(existing_handler)
        isolated_root_logger.setLevel(logging.ERROR)

        setup_logging()

        assert isolated_root_logger.handlers == [existing_handler]
        assert isolated_root_logger.level == logging.ERROR

    def test_writes_japanese_as_utf8(self, isolated_root_logger, tmp_path, monkeypatch):
        """日本語を UTF-8 のファイルへ文字化けせず出力する。"""
        isolated_root_logger.handlers.clear()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("comken.core.logger.today", lambda: date(2026, 8, 13))
        log_path = tmp_path / "logs" / "2026-08-13.log"

        setup_logging()
        logging.getLogger("sample").info("処理が完了しました")
        for handler in isolated_root_logger.handlers:
            handler.flush()

        log_text = log_path.read_text(encoding="utf-8")
        assert "INFO sample: 処理が完了しました" in log_text

    def test_skips_file_output(self, isolated_root_logger, tmp_path, monkeypatch):
        """to_file=False では logs フォルダもファイルも作らない。"""
        isolated_root_logger.handlers.clear()
        monkeypatch.chdir(tmp_path)

        setup_logging(to_file=False)

        assert len(isolated_root_logger.handlers) == 1
        assert type(isolated_root_logger.handlers[0]) is logging.StreamHandler
        assert not (tmp_path / "logs").exists()
