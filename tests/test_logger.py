"""新しい環境別・ローカルログ設定のテスト。"""

import importlib
import logging
import os
import socket
import sys
from datetime import date
from pathlib import Path

import pytest

from comken.core import logger
from comken.core.logger import Backoffice, Intranet, local, setup
from comken.core.logger.environment import setup as environment_setup
from comken.core.logger.site import LoggerSite
from comken.exceptions import (
    LoggerHostNotConfiguredError,
    LoggingAlreadyConfiguredError,
    SiteOwnerRequiredError,
)

local_module = importlib.import_module("comken.core.logger.local")


@pytest.fixture
def isolated_logging():
    """root logger の設定をテスト間で分離する。"""
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    original_level = root_logger.level
    root_logger.handlers.clear()
    try:
        yield root_logger
    finally:
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            handler.close()
        root_logger.handlers.extend(original_handlers)
        root_logger.setLevel(original_level)


def _prepare_site(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    logging.getLogger().handlers.clear()
    hostname = socket.gethostname()
    monkeypatch.setattr(Backoffice, "LOG_FOLDERS", {hostname: str(tmp_path)})
    monkeypatch.setattr(Intranet, "LOG_FOLDERS", {hostname: str(tmp_path)})
    monkeypatch.setattr("comken.core.logger.environment.today", lambda: date(2026, 8, 21))


class TestSetup:
    def test_package_exports_implementation_directly(self):
        assert logger.setup is environment_setup

    def test_backoffice_adds_root_handlers(self, isolated_logging, tmp_path, monkeypatch):
        _prepare_site(monkeypatch, tmp_path)
        setup(Backoffice)
        assert len(isolated_logging.handlers) == 2
        assert {handler.name for handler in isolated_logging.handlers} == {
            "comken.console",
            "comken.environment",
        }
        assert (tmp_path / "backoffice-2026-08-21.log").exists()

    def test_intranet_uses_its_name(self, isolated_logging, tmp_path, monkeypatch):
        _prepare_site(monkeypatch, tmp_path)
        setup(Intranet)
        assert (tmp_path / "intranet-2026-08-21.log").exists()

    def test_second_call_raises(self, isolated_logging, tmp_path, monkeypatch):
        _prepare_site(monkeypatch, tmp_path)
        setup(Backoffice)
        with pytest.raises(LoggingAlreadyConfiguredError):
            setup(Backoffice)

    def test_existing_handler_raises(self, isolated_logging):
        isolated_logging.handlers.clear()
        isolated_logging.addHandler(logging.StreamHandler())
        with pytest.raises(LoggingAlreadyConfiguredError):
            setup(Backoffice)

    def test_missing_owner_raises(self, isolated_logging):
        isolated_logging.handlers.clear()

        class OwnerMissing(LoggerSite):
            NAME = "missing"

        with pytest.raises(SiteOwnerRequiredError):
            setup(OwnerMissing)

    def test_output_includes_process_id(self, isolated_logging, tmp_path, monkeypatch):
        _prepare_site(monkeypatch, tmp_path)
        setup(Backoffice)
        logging.getLogger("sample").info("done")
        file_handler = next(
            handler
            for handler in isolated_logging.handlers
            if isinstance(handler, logging.FileHandler)
        )
        file_handler.flush()
        text = Path(file_handler.baseFilename).read_text(encoding="utf-8")
        assert f"[pid={os.getpid()}]" in text

    def test_unregistered_host_raises(self, isolated_logging, monkeypatch):
        isolated_logging.handlers.clear()
        monkeypatch.setattr(Backoffice, "LOG_FOLDERS", {})

        with pytest.raises(LoggerHostNotConfiguredError) as caught:
            setup(Backoffice)

        message = str(caught.value)
        assert socket.gethostname() in message
        assert Backoffice.NAME in message
        assert "LOG_FOLDERS" in message

    def test_writes_japanese_as_utf8(self, isolated_logging, tmp_path, monkeypatch):
        _prepare_site(monkeypatch, tmp_path)
        setup(Backoffice)
        logging.getLogger("sample").info("処理が完了しました")
        file_handler = next(
            handler
            for handler in isolated_logging.handlers
            if isinstance(handler, logging.FileHandler)
        )
        file_handler.flush()
        assert "処理が完了しました" in Path(file_handler.baseFilename).read_text(encoding="utf-8")


class TestLocal:
    def test_package_exports_implementation_directly(self):
        assert logger.local is local_module.local

    def _prepare(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        logging.getLogger().handlers.clear()
        monkeypatch.setattr(sys, "argv", [str(tmp_path / "main.py")])
        monkeypatch.setattr(local_module, "today", lambda: date(2026, 8, 21))

    def test_default_path(self, isolated_logging, tmp_path, monkeypatch):
        self._prepare(monkeypatch, tmp_path)
        local()
        assert (tmp_path / "logs" / "local-2026-08-21.log").exists()
        assert {handler.name for handler in isolated_logging.handlers} == {
            "comken.console",
            "comken.local",
        }

    def test_console_level_can_be_debug(self, isolated_logging, tmp_path, monkeypatch):
        self._prepare(monkeypatch, tmp_path)
        result = local(console_level=logger.DEBUG)
        stream_handler = next(
            handler
            for handler in isolated_logging.handlers
            if isinstance(handler, logging.StreamHandler)
            and not isinstance(handler, logging.FileHandler)
        )
        file_handler = next(
            handler
            for handler in isolated_logging.handlers
            if isinstance(handler, logging.FileHandler)
        )
        assert result is None
        assert stream_handler.level == logging.DEBUG
        assert file_handler.level == logging.INFO

    def test_file_level_can_be_debug(self, isolated_logging, tmp_path, monkeypatch):
        self._prepare(monkeypatch, tmp_path)
        local(file_level=logger.DEBUG)
        stream_handler = next(
            handler
            for handler in isolated_logging.handlers
            if isinstance(handler, logging.StreamHandler)
            and not isinstance(handler, logging.FileHandler)
        )
        file_handler = next(
            handler
            for handler in isolated_logging.handlers
            if isinstance(handler, logging.FileHandler)
        )
        assert stream_handler.level == logging.INFO
        assert file_handler.level == logging.DEBUG

    def test_custom_path(self, isolated_logging, tmp_path, monkeypatch):
        self._prepare(monkeypatch, tmp_path)
        custom_path = tmp_path / "custom" / "logs"
        local(path=custom_path)
        assert (custom_path / "local-2026-08-21.log").exists()

    def test_relative_path_uses_project_dir(self, isolated_logging, tmp_path, monkeypatch):
        self._prepare(monkeypatch, tmp_path)
        local(path="custom-logs")
        assert (tmp_path / "custom-logs" / "local-2026-08-21.log").exists()

    def test_after_setup_reuses_console(self, isolated_logging, tmp_path, monkeypatch):
        _prepare_site(monkeypatch, tmp_path)
        setup(Backoffice)
        console_handler = next(
            handler
            for handler in isolated_logging.handlers
            if isinstance(handler, logging.StreamHandler)
            and not isinstance(handler, logging.FileHandler)
        )

        monkeypatch.setattr(sys, "argv", [str(tmp_path / "main.py")])
        monkeypatch.setattr(local_module, "today", lambda: date(2026, 8, 21))
        local(console_level=logging.DEBUG, file_level=logging.WARNING)

        assert len(isolated_logging.handlers) == 3
        assert isolated_logging.handlers.count(console_handler) == 1
        assert {handler.name for handler in isolated_logging.handlers} == {
            "comken.console",
            "comken.environment",
            "comken.local",
        }
        assert console_handler.level == logging.DEBUG
        assert isolated_logging.level == logging.DEBUG

    def test_unknown_handler_configuration_raises(self, isolated_logging):
        console_handler = logging.StreamHandler()
        console_handler.set_name("comken.console")
        unknown_file_handler = logging.FileHandler(os.devnull, encoding="utf-8")
        unknown_file_handler.set_name("unknown")
        isolated_logging.addHandler(console_handler)
        isolated_logging.addHandler(unknown_file_handler)

        try:
            with pytest.raises(LoggingAlreadyConfiguredError):
                local()
        finally:
            isolated_logging.removeHandler(unknown_file_handler)
            unknown_file_handler.close()

    def test_second_call_raises(self, isolated_logging, tmp_path, monkeypatch):
        self._prepare(monkeypatch, tmp_path)
        local()
        with pytest.raises(LoggingAlreadyConfiguredError):
            local()

    def test_setup_after_local_raises(self, isolated_logging, tmp_path, monkeypatch):
        self._prepare(monkeypatch, tmp_path)
        local()
        with pytest.raises(LoggingAlreadyConfiguredError):
            setup(Backoffice)

    def test_existing_handler_raises(self, isolated_logging):
        isolated_logging.addHandler(logging.StreamHandler())

        with pytest.raises(LoggingAlreadyConfiguredError):
            local()

    def test_output_includes_process_id(self, isolated_logging, tmp_path, monkeypatch):
        self._prepare(monkeypatch, tmp_path)
        local()
        module_logger = logging.getLogger("sample.module")
        module_logger.info("done")
        file_handler = next(
            handler
            for handler in isolated_logging.handlers
            if isinstance(handler, logging.FileHandler)
        )
        file_handler.flush()
        text = Path(file_handler.baseFilename).read_text(encoding="utf-8")
        assert f"[pid={os.getpid()}]" in text
        assert "sample.module: done" in text
