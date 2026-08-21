"""新しい環境別・ローカルログ設定のテスト。"""

import logging
import socket
import sys
from datetime import date
from pathlib import Path

import pytest

from comken.core import logger
from comken.core.logger import Backoffice, Intranet, local, setup_logging
from comken.core.logger._env import CsvFormatter
from comken.core.logger._run_id import current_run_id
from comken.core.logger._site import LoggerSite
from comken.exceptions import LoggingAlreadyConfiguredError, SiteOwnerRequiredError


@pytest.fixture
def isolated_logging():
    """root logger と local logger の設定をテスト間で分離する。"""
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    original_level = root_logger.level
    root_logger.handlers.clear()
    try:
        yield root_logger
    finally:
        loggers = [root_logger]
        loggers.extend(
            value
            for value in logging.Logger.manager.loggerDict.values()
            if isinstance(value, logging.Logger) and value.name.startswith("comken.local.")
        )
        for target_logger in loggers:
            for handler in target_logger.handlers[:]:
                target_logger.removeHandler(handler)
                handler.close()
        root_logger.handlers.extend(original_handlers)
        root_logger.setLevel(original_level)


def _prepare_site(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    logging.getLogger().handlers.clear()
    monkeypatch.setattr(Backoffice, "LOG_PATH", tmp_path)
    monkeypatch.setattr(Intranet, "LOG_PATH", tmp_path)
    monkeypatch.setattr("comken.core.logger._env.today", lambda: date(2026, 8, 21))


class TestSetupLogging:
    def test_backoffice_adds_root_handlers(self, isolated_logging, tmp_path, monkeypatch):
        _prepare_site(monkeypatch, tmp_path)
        setup_logging(Backoffice)
        assert len(isolated_logging.handlers) == 2
        assert (tmp_path / socket.gethostname() / "backoffice-2026-08-21.log").exists()

    def test_intranet_uses_its_name(self, isolated_logging, tmp_path, monkeypatch):
        _prepare_site(monkeypatch, tmp_path)
        setup_logging(Intranet)
        assert (tmp_path / socket.gethostname() / "intranet-2026-08-21.log").exists()

    def test_second_call_raises(self, isolated_logging, tmp_path, monkeypatch):
        _prepare_site(monkeypatch, tmp_path)
        setup_logging(Backoffice)
        with pytest.raises(LoggingAlreadyConfiguredError):
            setup_logging(Backoffice)

    def test_existing_handler_raises(self, isolated_logging):
        isolated_logging.handlers.clear()
        isolated_logging.addHandler(logging.StreamHandler())
        with pytest.raises(LoggingAlreadyConfiguredError):
            setup_logging(Backoffice)

    def test_missing_owner_raises(self, isolated_logging):
        isolated_logging.handlers.clear()

        class OwnerMissing(LoggerSite):
            NAME = "missing"

        with pytest.raises(SiteOwnerRequiredError):
            setup_logging(OwnerMissing)

    def test_run_id_is_injected_into_every_output(self, isolated_logging, tmp_path, monkeypatch):
        _prepare_site(monkeypatch, tmp_path)
        setup_logging(Backoffice)
        logging.getLogger("sample").info("done")
        file_handler = next(
            handler
            for handler in isolated_logging.handlers
            if isinstance(handler, logging.FileHandler)
        )
        file_handler.flush()
        text = Path(file_handler.baseFilename).read_text(encoding="utf-8")
        assert current_run_id()
        assert f"run_id={current_run_id()}" in text

    def test_csv_fields_use_csv_formatter(self, isolated_logging, tmp_path, monkeypatch):
        isolated_logging.handlers.clear()

        class CsvSite(LoggerSite):
            NAME = "csv"
            LOG_PATH = tmp_path
            CSV_FIELDS = ("levelname", "message", "run_id")
            OWNER = "テスト / 担当者"

        monkeypatch.setattr("comken.core.logger._env.today", lambda: date(2026, 8, 21))
        setup_logging(CsvSite)
        logging.getLogger("sample").warning("日本語,カンマ")
        file_handler = next(
            handler
            for handler in isolated_logging.handlers
            if isinstance(handler, logging.FileHandler)
        )
        file_handler.flush()
        assert isinstance(file_handler.formatter, CsvFormatter)
        assert 'WARNING,"日本語,カンマ",' in Path(file_handler.baseFilename).read_text(
            encoding="utf-8"
        )

    def test_writes_japanese_as_utf8(self, isolated_logging, tmp_path, monkeypatch):
        _prepare_site(monkeypatch, tmp_path)
        setup_logging(Backoffice)
        logging.getLogger("sample").info("処理が完了しました")
        file_handler = next(
            handler
            for handler in isolated_logging.handlers
            if isinstance(handler, logging.FileHandler)
        )
        file_handler.flush()
        assert "処理が完了しました" in Path(file_handler.baseFilename).read_text(encoding="utf-8")

    def test_setup_short_name_is_available(self, isolated_logging, tmp_path, monkeypatch):
        _prepare_site(monkeypatch, tmp_path)
        logger.setup(Backoffice)
        assert len(isolated_logging.handlers) == 2


class TestLocal:
    def _prepare(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(sys, "argv", [str(tmp_path / "main.py")])
        monkeypatch.setattr("comken.core.logger._local.today", lambda: date(2026, 8, 21))

    def test_default_path(self, isolated_logging, tmp_path, monkeypatch):
        self._prepare(monkeypatch, tmp_path)
        local()
        assert (tmp_path / "logs" / "local-2026-08-21.log").exists()

    def test_console_level_can_be_debug(self, isolated_logging, tmp_path, monkeypatch):
        self._prepare(monkeypatch, tmp_path)
        configured = local(console_level=logger.DEBUG)
        stream_handler = next(
            handler for handler in configured.handlers if type(handler) is logging.StreamHandler
        )
        file_handler = next(
            handler for handler in configured.handlers if isinstance(handler, logging.FileHandler)
        )
        assert stream_handler.level == logging.DEBUG
        assert file_handler.level == logging.INFO

    def test_file_level_can_be_debug(self, isolated_logging, tmp_path, monkeypatch):
        self._prepare(monkeypatch, tmp_path)
        configured = local(file_level=logger.DEBUG)
        stream_handler = next(
            handler for handler in configured.handlers if type(handler) is logging.StreamHandler
        )
        file_handler = next(
            handler for handler in configured.handlers if isinstance(handler, logging.FileHandler)
        )
        assert stream_handler.level == logging.INFO
        assert file_handler.level == logging.DEBUG

    def test_custom_path(self, isolated_logging, tmp_path, monkeypatch):
        self._prepare(monkeypatch, tmp_path)
        custom_path = tmp_path / "custom" / "logs"
        local(path=custom_path)
        assert (custom_path / "local-2026-08-21.log").exists()

    def test_can_be_called_more_than_once(self, isolated_logging, tmp_path, monkeypatch):
        self._prepare(monkeypatch, tmp_path)
        first = local()
        second = local()
        assert first is second
        assert len(second.handlers) == 2
