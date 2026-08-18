"""単体実行向けログ設定のテスト。"""

import logging
import sys
from datetime import date

import pytest

from comken.core.logger import setup_logging
from comken.core.logging_run_id import (
    RunIdFilter,
    current_run_id,
    new_run_id,
)


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
        # ログは project_dir()（main.py の場所）へ出る。chdir だけでは向き先が変わらない
        monkeypatch.setattr(sys, "argv", [str(tmp_path / "main.py")])
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
        # ログは project_dir()（main.py の場所）へ出る。chdir だけでは向き先が変わらない
        monkeypatch.setattr(sys, "argv", [str(tmp_path / "main.py")])
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
        # ログは project_dir()（main.py の場所）へ出る。chdir だけでは向き先が変わらない
        monkeypatch.setattr(sys, "argv", [str(tmp_path / "main.py")])

        setup_logging(to_file=False)

        assert len(isolated_root_logger.handlers) == 1
        assert type(isolated_root_logger.handlers[0]) is logging.StreamHandler
        assert not (tmp_path / "logs").exists()


# ── run_id ────────────────────────────────────────────────────────────────────


@pytest.fixture
def reset_run_id():
    """run_id のコンテキスト変数をテスト後にリセットする。"""
    from comken.core import logging_run_id

    token = logging_run_id._RUN_ID_VAR.set(None)
    try:
        yield
    finally:
        logging_run_id._RUN_ID_VAR.reset(token)


class TestRunId:
    def test_new_run_id_returns_string(self, reset_run_id) -> None:
        """new_run_id() は 8 文字の hex 文字列を返す。"""
        run_id = new_run_id()
        assert isinstance(run_id, str)
        assert len(run_id) == 8
        # hex 文字列 (0-9, a-f) のみ
        assert all(c in "0123456789abcdef" for c in run_id)

    def test_new_run_id_sets_context(self, reset_run_id) -> None:
        """new_run_id() で発行した ID が current_run_id() で取れる。"""
        run_id = new_run_id()
        assert current_run_id() == run_id

    def test_current_run_id_returns_dash_when_unset(self, reset_run_id) -> None:
        """コンテキストに無いときは "-" を返す。"""
        # reset_run_id フィクスチャで None に戻した直後
        assert current_run_id() == "-"

    def test_run_id_filter_injects_attribute(self, reset_run_id) -> None:
        """RunIdFilter が LogRecord に run_id を入れる。"""
        run_id = new_run_id()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=0,
            msg="msg",
            args=(),
            exc_info=None,
        )
        RunIdFilter().filter(record)
        assert record.run_id == run_id

    def test_run_id_filter_respects_extra(self, reset_run_id) -> None:
        """extra={"run_id": ...} を渡したときはそちらを優先する。"""
        new_run_id()  # コンテキストに ID を入れる
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=0,
            msg="msg",
            args=(),
            exc_info=None,
        )
        record.run_id = "manual-id"  # extra を模倣
        RunIdFilter().filter(record)
        assert record.run_id == "manual-id"

    def test_run_id_appears_in_log_output(
        self, isolated_root_logger, tmp_path, monkeypatch, reset_run_id
    ) -> None:
        """ログ出力に [RUN:xxxxx] プレフィックスが含まれる。"""
        isolated_root_logger.handlers.clear()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", [str(tmp_path / "main.py")])
        monkeypatch.setattr("comken.core.logger.today", lambda: date(2026, 8, 13))

        run_id = new_run_id()
        setup_logging()
        logging.getLogger("sample").info("処理開始")

        for handler in isolated_root_logger.handlers:
            handler.flush()

        log_text = (tmp_path / "logs" / "2026-08-13.log").read_text(encoding="utf-8")
        assert f"[RUN:{run_id}]" in log_text

    def test_run_id_dash_when_not_initialized(
        self, isolated_root_logger, tmp_path, monkeypatch, reset_run_id
    ) -> None:
        """new_run_id() を呼ばずにログを出したとき、[RUN:-] になる。"""
        isolated_root_logger.handlers.clear()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", [str(tmp_path / "main.py")])
        monkeypatch.setattr("comken.core.logger.today", lambda: date(2026, 8, 13))

        setup_logging()
        logging.getLogger("sample").info("処理開始")

        for handler in isolated_root_logger.handlers:
            handler.flush()

        log_text = (tmp_path / "logs" / "2026-08-13.log").read_text(encoding="utf-8")
        assert "[RUN:-]" in log_text
