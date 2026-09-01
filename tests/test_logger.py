"""新しい環境別・ローカルログ設定のテスト。"""

import datetime
import importlib
import logging
import os
import socket
import sys
from datetime import date
from pathlib import Path

import pytest

from comken.core import logger
from comken.core.logger import Backoffice, Intranet, setup_local_logging, setup_logging
from comken.core.logger.environment import (
    CONSOLE_HANDLER_NAME,
    ENVIRONMENT_HANDLER_NAME,
    LOCAL_HANDLER_NAME,
    _build_log_filename,
    _format_external_handlers,
)
from comken.core.logger.environment import (
    setup_logging as environment_setup_logging,
)
from comken.core.logger.site import LoggerSite
from comken.exceptions import (
    LoggingAlreadyConfiguredError,
    LoggingConflictError,
    LogRootNotConfiguredError,
    SiteOwnerRequiredError,
)

local_module = importlib.import_module("comken.core.logger.local")

# テスト全体で固定する now()/today()。ファイル名にはマイクロ秒と
# 日付フォルダ名（today().isoformat()）の両方が入るため、両方を
# 同じ値に揃えておかないとテストの assertion が通らない。
# ``strftime()`` はタイムゾーンに依存しないので、tzinfo を ``UTC`` に
# 固定して ``DTZ001`` を満たす（テスト用途の固定値で、実環境の
# タイムゾーンでも strftime の結果は変わらない）。
_FIXED_NOW = datetime.datetime(
    2026, 8, 21, 10, 30, 45, 123456, tzinfo=datetime.UTC
)
_FIXED_TODAY = date(2026, 8, 21)
# 固定値を 1 か所にまとめて typo を防ぐ。
_FIXED_LOG_FILENAME = f"{_FIXED_NOW.strftime('%Y%m%d_%H%M%S_%f')}_{os.getpid()}.log"


class _LogCapture(logging.Handler):
    """テスト用に root ログをメモリへ捕捉するハンドラー。"""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


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
    """LOG_ROOT を一時ディレクトリに向け、now()/today() を固定する。

    フォルダ名は実行端末のホスト名（小文字） から自動で決まるため、
    テスト側で用意する必要はない。各テストで必要なら
    ``tmp_path / socket.gethostname().lower() / "python" / "2026-08-21"``
    のように組み立てる。ファイル名は ``_FIXED_LOG_FILENAME`` になる。
    """
    logging.getLogger().handlers.clear()
    for site in (Backoffice, Intranet):
        monkeypatch.setattr(site, "LOG_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "comken.core.logger.environment.today",
        lambda: _FIXED_TODAY,
    )
    monkeypatch.setattr(
        "comken.core.logger.environment.now",
        lambda: _FIXED_NOW,
    )


def _environment_log_dir(tmp_path: Path) -> Path:
    """hostname/python/{today()} の構造で出来上がるログディレクトリの絶対パス。"""
    return tmp_path / socket.gethostname().lower() / "python" / _FIXED_TODAY.isoformat()


class TestSetup:
    def test_package_exports_implementation_directly(self):
        assert logger.setup_logging is environment_setup_logging

    def test_backoffice_adds_root_handlers(self, isolated_logging, tmp_path, monkeypatch):
        _prepare_site(monkeypatch, tmp_path)
        setup_logging(Backoffice)
        assert len(isolated_logging.handlers) == 2
        assert {handler.name for handler in isolated_logging.handlers} == {
            CONSOLE_HANDLER_NAME,
            ENVIRONMENT_HANDLER_NAME,
        }
        # ファイル名が動的なので、フォルダを作ってファイルが 1 件だけ存在することを確認する。
        log_dir = _environment_log_dir(tmp_path)
        assert log_dir.is_dir()
        files = list(log_dir.glob("*.log"))
        assert len(files) == 1

    def test_second_call_raises(self, isolated_logging, tmp_path, monkeypatch):
        _prepare_site(monkeypatch, tmp_path)
        setup_logging(Backoffice)
        with pytest.raises(LoggingAlreadyConfiguredError):
            setup_logging(Backoffice)

    def test_existing_handler_raises(self, isolated_logging):
        isolated_logging.handlers.clear()
        isolated_logging.addHandler(logging.StreamHandler())
        with pytest.raises(LoggingConflictError):
            setup_logging(Backoffice)

    def test_missing_owner_raises(self, isolated_logging):
        isolated_logging.handlers.clear()

        class OwnerMissing(LoggerSite):
            pass

        with pytest.raises(SiteOwnerRequiredError):
            setup_logging(OwnerMissing)

    def test_missing_log_root_raises_before_creating_files(
        self, isolated_logging, tmp_path, monkeypatch
    ):
        """LOG_ROOT が空のときは、ファイルを作る前に例外で止まる。"""
        logging.getLogger().handlers.clear()
        monkeypatch.setattr(Backoffice, "LOG_ROOT", "")

        with pytest.raises(LogRootNotConfiguredError):
            setup_logging(Backoffice)

        # 空フォルダすら作られていないことを確認（運用側に空フォルダを残さない）。
        assert list(tmp_path.iterdir()) == []

    def test_output_includes_process_id(self, isolated_logging, tmp_path, monkeypatch):
        """ログ本文ではなくファイル名に PID が入ることで同時実行プロセスを見分けられる。"""
        _prepare_site(monkeypatch, tmp_path)
        setup_logging(Backoffice)
        file_handler = next(
            handler
            for handler in isolated_logging.handlers
            if isinstance(handler, logging.FileHandler)
        )
        file_handler.flush()
        log_path = Path(file_handler.baseFilename)
        assert log_path.name == _FIXED_LOG_FILENAME
        # ファイル名に PID が入っており、ログ本文には PID が含まれない（新設計）。
        assert f"_{os.getpid()}.log" in log_path.name
        text = log_path.read_text(encoding="utf-8")
        assert f"[pid={os.getpid()}]" not in text

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


class TestLocal:
    def test_package_exports_implementation_directly(self):
        assert logger.setup_local_logging is local_module.setup_local_logging

    def _prepare(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """setup_local_logging() 用: project_dir() 起点 + now()/today() を固定する。

        now()/today() は ``_build_log_filename()`` と local.py の保存先組み立てが
        それぞれ参照するため、environment 側（``now``）と local 側（``today``）の両方を
        固定する必要がある（同じ関数を再 import した別名になっている）。
        """
        logging.getLogger().handlers.clear()
        monkeypatch.setattr(sys, "argv", [str(tmp_path / "main.py")])
        monkeypatch.setattr(local_module, "today", lambda: _FIXED_TODAY)
        monkeypatch.setattr(
            "comken.core.logger.environment.today",
            lambda: _FIXED_TODAY,
        )
        monkeypatch.setattr(
            "comken.core.logger.environment.now",
            lambda: _FIXED_NOW,
        )

    def test_default_path(self, isolated_logging, tmp_path, monkeypatch):
        self._prepare(monkeypatch, tmp_path)
        setup_local_logging()
        log_dir = tmp_path / "logs" / _FIXED_TODAY.isoformat()
        assert log_dir.is_dir()
        files = list(log_dir.glob("*.log"))
        assert len(files) == 1
        assert {handler.name for handler in isolated_logging.handlers} == {
            CONSOLE_HANDLER_NAME,
            LOCAL_HANDLER_NAME,
        }

    def test_console_level_can_be_debug(self, isolated_logging, tmp_path, monkeypatch):
        self._prepare(monkeypatch, tmp_path)
        result = setup_local_logging(console_level=logging.DEBUG)
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
        setup_local_logging(file_level=logging.DEBUG)
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
        setup_local_logging(path=custom_path)
        log_dir = custom_path / _FIXED_TODAY.isoformat()
        assert log_dir.is_dir()
        assert len(list(log_dir.glob("*.log"))) == 1

    def test_relative_path_uses_project_dir(self, isolated_logging, tmp_path, monkeypatch):
        self._prepare(monkeypatch, tmp_path)
        setup_local_logging(path="custom-logs")
        log_dir = tmp_path / "custom-logs" / _FIXED_TODAY.isoformat()
        assert log_dir.is_dir()
        assert len(list(log_dir.glob("*.log"))) == 1

    def test_after_setup_reuses_console(self, isolated_logging, tmp_path, monkeypatch):
        _prepare_site(monkeypatch, tmp_path)
        setup_logging(Backoffice)
        console_handler = next(
            handler
            for handler in isolated_logging.handlers
            if isinstance(handler, logging.StreamHandler)
            and not isinstance(handler, logging.FileHandler)
        )

        monkeypatch.setattr(sys, "argv", [str(tmp_path / "main.py")])
        monkeypatch.setattr(local_module, "today", lambda: _FIXED_TODAY)
        monkeypatch.setattr(
            "comken.core.logger.environment.today",
            lambda: _FIXED_TODAY,
        )
        monkeypatch.setattr(
            "comken.core.logger.environment.now",
            lambda: _FIXED_NOW,
        )
        setup_local_logging(console_level=logging.DEBUG, file_level=logging.WARNING)

        assert len(isolated_logging.handlers) == 3
        assert isolated_logging.handlers.count(console_handler) == 1
        assert {handler.name for handler in isolated_logging.handlers} == {
            CONSOLE_HANDLER_NAME,
            ENVIRONMENT_HANDLER_NAME,
            LOCAL_HANDLER_NAME,
        }
        assert console_handler.level == logging.DEBUG
        assert isolated_logging.level == logging.DEBUG
        # setup_logging() 側のログファイルが hostname/python/{date} 配下に作られている。
        env_log_dir = _environment_log_dir(tmp_path)
        assert env_log_dir.is_dir()
        assert len(list(env_log_dir.glob("*.log"))) == 1

    def test_local_then_setup_reuses_console(self, isolated_logging, tmp_path, monkeypatch):
        """setup_local_logging() → setup_logging() の順でも動き、console は二重にならない。"""
        _prepare_site(monkeypatch, tmp_path)
        monkeypatch.setattr(sys, "argv", [str(tmp_path / "main.py")])
        monkeypatch.setattr(local_module, "today", lambda: _FIXED_TODAY)
        monkeypatch.setattr(
            "comken.core.logger.environment.today",
            lambda: _FIXED_TODAY,
        )
        monkeypatch.setattr(
            "comken.core.logger.environment.now",
            lambda: _FIXED_NOW,
        )

        setup_local_logging(console_level=logging.DEBUG, file_level=logging.WARNING)
        setup_logging(Backoffice)

        assert {handler.name for handler in isolated_logging.handlers} == {
            CONSOLE_HANDLER_NAME,
            ENVIRONMENT_HANDLER_NAME,
            LOCAL_HANDLER_NAME,
        }
        console_handler = next(
            h for h in isolated_logging.handlers if h.name == CONSOLE_HANDLER_NAME
        )
        environment_handler = next(
            h for h in isolated_logging.handlers if h.name == ENVIRONMENT_HANDLER_NAME
        )
        local_handler = next(h for h in isolated_logging.handlers if h.name == LOCAL_HANDLER_NAME)
        # setup_local_logging() が決めた console_level を setup_logging() が上書きしない。
        assert console_handler.level == logging.DEBUG
        assert environment_handler.level == logging.INFO
        assert local_handler.level == logging.WARNING

    def test_setup_then_local_then_setup_raises(self, isolated_logging, tmp_path, monkeypatch):
        """setup_logging() → setup_local_logging() → setup_logging() の順は
        3 つ目を足す操作なので例外。"""
        _prepare_site(monkeypatch, tmp_path)
        setup_logging(Backoffice)
        monkeypatch.setattr(sys, "argv", [str(tmp_path / "main.py")])
        monkeypatch.setattr(local_module, "today", lambda: _FIXED_TODAY)
        monkeypatch.setattr(
            "comken.core.logger.environment.today",
            lambda: _FIXED_TODAY,
        )
        monkeypatch.setattr(
            "comken.core.logger.environment.now",
            lambda: _FIXED_NOW,
        )
        setup_local_logging()

        with pytest.raises(LoggingAlreadyConfiguredError):
            setup_logging(Backoffice)

    def test_setup_then_local_then_local_raises(self, isolated_logging, tmp_path, monkeypatch):
        """setup_logging() → setup_local_logging() → setup_local_logging() の順も
        3 つ目を足す操作なので例外。"""
        _prepare_site(monkeypatch, tmp_path)
        setup_logging(Backoffice)
        monkeypatch.setattr(sys, "argv", [str(tmp_path / "main.py")])
        monkeypatch.setattr(local_module, "today", lambda: _FIXED_TODAY)
        monkeypatch.setattr(
            "comken.core.logger.environment.today",
            lambda: _FIXED_TODAY,
        )
        monkeypatch.setattr(
            "comken.core.logger.environment.now",
            lambda: _FIXED_NOW,
        )
        setup_local_logging()

        with pytest.raises(LoggingAlreadyConfiguredError):
            setup_local_logging()

    def test_unknown_handler_configuration_raises(self, isolated_logging):
        console_handler = logging.StreamHandler()
        console_handler.set_name("comken.console")
        unknown_file_handler = logging.FileHandler(os.devnull, encoding="utf-8")
        unknown_file_handler.set_name("unknown")
        isolated_logging.addHandler(console_handler)
        isolated_logging.addHandler(unknown_file_handler)

        try:
            with pytest.raises(LoggingConflictError):
                setup_local_logging()
        finally:
            isolated_logging.removeHandler(unknown_file_handler)
            unknown_file_handler.close()

    def test_external_handler_raises_at_setup_logging(
        self, isolated_logging, tmp_path, monkeypatch
    ):
        """外部ハンドラーが混ざっている状態で setup_logging() を呼ぶと例外。"""
        _prepare_site(monkeypatch, tmp_path)
        external = logging.StreamHandler()
        external.set_name("external.library")
        isolated_logging.addHandler(external)
        try:
            with pytest.raises(LoggingConflictError):
                setup_logging(Backoffice)
        finally:
            isolated_logging.removeHandler(external)
            external.close()

    def test_second_call_raises(self, isolated_logging, tmp_path, monkeypatch):
        self._prepare(monkeypatch, tmp_path)
        setup_local_logging()
        with pytest.raises(LoggingAlreadyConfiguredError):
            setup_local_logging()

    def test_external_handler_raises_at_setup_local_logging(self, isolated_logging):
        isolated_logging.addHandler(logging.StreamHandler())
        try:
            with pytest.raises(LoggingConflictError):
                setup_local_logging()
        finally:
            for h in isolated_logging.handlers[:]:
                isolated_logging.removeHandler(h)
                h.close()

    def test_output_includes_process_id(self, isolated_logging, tmp_path, monkeypatch):
        """ログ本文ではなくファイル名に PID が入ることで同時実行プロセスを見分けられる。"""
        self._prepare(monkeypatch, tmp_path)
        setup_local_logging()
        module_logger = logging.getLogger("sample.module")
        module_logger.info("done")
        file_handler = next(
            handler
            for handler in isolated_logging.handlers
            if isinstance(handler, logging.FileHandler)
        )
        file_handler.flush()
        log_path = Path(file_handler.baseFilename)
        assert log_path.name == _FIXED_LOG_FILENAME
        assert f"_{os.getpid()}.log" in log_path.name
        text = log_path.read_text(encoding="utf-8")
        # 本文に PID を含まない（新設計）。
        assert f"[pid={os.getpid()}]" not in text
        assert "sample.module: done" in text

    def test_root_level_is_min_of_own_handlers_alone(self, isolated_logging, tmp_path, monkeypatch):
        """setup_local_logging() 単独呼び出しで root level は INFO
        （=自分の handler の min）になる。"""
        self._prepare(monkeypatch, tmp_path)
        setup_local_logging()
        assert isolated_logging.level == logging.INFO

    def test_root_level_uses_lower_of_console_and_file(
        self, isolated_logging, tmp_path, monkeypatch
    ):
        """console_level と file_level が異なるとき、root は低い方になる。"""
        self._prepare(monkeypatch, tmp_path)
        setup_local_logging(console_level=logging.WARNING, file_level=logging.DEBUG)
        assert isolated_logging.level == logging.DEBUG

        self._prepare(monkeypatch, tmp_path)
        setup_local_logging(console_level=logging.DEBUG, file_level=logging.WARNING)
        assert isolated_logging.level == logging.DEBUG

    def test_root_level_after_setup_and_local_is_min_of_three(
        self, isolated_logging, tmp_path, monkeypatch
    ):
        """setup_logging() と setup_local_logging() が両方走った後は
        console / environment / local の min。"""
        _prepare_site(monkeypatch, tmp_path)
        monkeypatch.setattr(sys, "argv", [str(tmp_path / "main.py")])
        monkeypatch.setattr(local_module, "today", lambda: _FIXED_TODAY)
        monkeypatch.setattr(
            "comken.core.logger.environment.today",
            lambda: _FIXED_TODAY,
        )
        monkeypatch.setattr(
            "comken.core.logger.environment.now",
            lambda: _FIXED_NOW,
        )

        setup_local_logging(console_level=logging.DEBUG, file_level=logging.WARNING)
        setup_logging(Backoffice)

        # INFO (env), DEBUG (console), WARNING (local) → DEBUG
        assert isolated_logging.level == logging.DEBUG

    def test_external_notset_handler_does_not_make_root_notset(
        self, isolated_logging, tmp_path, monkeypatch
    ):
        """外部の NOTSET ハンドラーが root に追加されても root は NOTSET にならない。

        修正前は root_logger.handlers 全体から min() を取るため、外部の
        NOTSET(0) ハンドラーが混ざると root が NOTSET に巻き戻され、
        isEnabledFor() が DEBUG まで通す穴になっていた。

        ここでは setup_local_logging() 内で local_file_handler が root に追加された直後に
        外部 NOTSET ハンドラーが追加される状況を monkey-patch で再現する
        （実際の経路: setup 後に import 副作用でハンドラーが足される等）。
        """
        _prepare_site(monkeypatch, tmp_path)
        setup_logging(Backoffice)

        external_handler = logging.StreamHandler()
        # logging.StreamHandler のデフォルト level は NOTSET(0)。
        assert external_handler.level == logging.NOTSET

        real_add_handler = isolated_logging.addHandler

        def patched_add_handler(handler: logging.Handler) -> None:
            real_add_handler(handler)
            if handler.name == local_module.LOCAL_HANDLER_NAME:
                real_add_handler(external_handler)

        monkeypatch.setattr(isolated_logging, "addHandler", patched_add_handler)

        monkeypatch.setattr(sys, "argv", [str(tmp_path / "main.py")])
        monkeypatch.setattr(local_module, "today", lambda: _FIXED_TODAY)
        monkeypatch.setattr(
            "comken.core.logger.environment.today",
            lambda: _FIXED_TODAY,
        )
        monkeypatch.setattr(
            "comken.core.logger.environment.now",
            lambda: _FIXED_NOW,
        )
        setup_local_logging()

        # 外部ハンドラーが root に付いていることを確認（テスト自体が穴を再現できているか）。
        assert external_handler in isolated_logging.handlers
        # 修正前は NOTSET になっていた。修正後は自分の handler の低い方 (INFO) になる。
        assert isolated_logging.level != logging.NOTSET
        assert isolated_logging.level == logging.INFO


class TestOwner:
    """LoggerSite.OWNER が comken 共通の規約に従うことのテスト。"""

    def test_backoffice_owner_is_comken(self):
        assert Backoffice.OWNER == "comken"

    def test_intranet_owner_is_comken(self):
        assert Intranet.OWNER == "comken"


class TestSiteClassShape:
    """LoggerSite / Backoffice / Intranet のクラス形状に関するテスト。

    旧 ``NAME`` / ``LOG_FOLDER_NAMES`` を削除したため、誤って復活しないことを
    保証する。新設計ではフォルダ名は実行端末のホスト名から作るため、
    クラス側に登録情報を持たない。
    """

    @pytest.mark.parametrize("site_cls", [LoggerSite, Backoffice, Intranet])
    def test_has_no_name_attribute(self, site_cls: type[LoggerSite]) -> None:
        assert not hasattr(site_cls, "NAME")

    @pytest.mark.parametrize("site_cls", [LoggerSite, Backoffice, Intranet])
    def test_has_no_log_folder_names_attribute(self, site_cls: type[LoggerSite]) -> None:
        assert not hasattr(site_cls, "LOG_FOLDER_NAMES")

    def test_backoffice_and_intranet_differ_only_in_log_root(self, monkeypatch) -> None:
        """Backoffice と Intranet の差分は ``LOG_ROOT`` などの設定値だけである。

        旧設計では ``NAME`` / ``LOG_FOLDER_NAMES`` もあったため、独自属性が
        ``{NAME, LOG_ROOT, LOG_FOLDER_NAMES, OWNER}`` だったが、新設計では
        ``{LOG_ROOT, OWNER}`` だけであることを見る。``vars()`` には
        ``__doc__`` などの Python 特殊属性も含まれるので、``__`` で始まらない
        ものだけを独自属性とみなす。
        """

        def own_attrs(cls: type) -> set[str]:
            # `__` で始まる特殊属性を除いたうえで、メソッド（関数 /
            # classmethod / staticmethod）も除外し、クラス変数だけを残す。
            # `classmethod` の descriptor は ``callable()`` が ``False`` を
            # 返すので、``callable()`` だけだと除外しきれない。
            return {
                name
                for name, value in vars(cls).items()
                if not name.startswith("__")
                and not isinstance(value, (classmethod, staticmethod))
                and not (callable(value) and not isinstance(value, type))
            }

        # Backoffice と Intranet の「独自設定」は LOG_ROOT と OWNER だけである
        # （旧設計の NAME / LOG_FOLDER_NAMES は廃止済み）。
        assert own_attrs(Backoffice) <= {"LOG_ROOT", "OWNER"}
        assert own_attrs(Intranet) <= {"LOG_ROOT", "OWNER"}
        # 両者の独自属性集合は同じ（差分は LOG_ROOT の値のみで、形ではない）。
        assert own_attrs(Backoffice) == own_attrs(Intranet)
        # LoggerSite 基底でも同様に LOG_ROOT と OWNER だけが宣言されている。
        assert own_attrs(LoggerSite) <= {"LOG_ROOT", "OWNER"}


class TestLogFilenameBuilder:
    """``_build_log_filename()`` の単体テスト。"""

    def test_filename_contains_microseconds_and_pid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """now() を固定したとき、``YYYYMMDD_HHMMSS_ffffff_<PID>.log`` 形式になる。"""
        monkeypatch.setattr(
            "comken.core.logger.environment.now",
            lambda: _FIXED_NOW,
        )
        assert _build_log_filename() == _FIXED_LOG_FILENAME

    def test_filename_differs_when_now_differs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """now() がマイクロ秒違うだけでも別のファイル名になる（衝突回避）。"""
        first = datetime.datetime(2026, 8, 21, 10, 30, 45, 123456, tzinfo=datetime.UTC)
        second = datetime.datetime(2026, 8, 21, 10, 30, 45, 654321, tzinfo=datetime.UTC)
        monkeypatch.setattr("comken.core.logger.environment.now", lambda: first)
        name1 = _build_log_filename()
        monkeypatch.setattr("comken.core.logger.environment.now", lambda: second)
        name2 = _build_log_filename()
        assert name1 != name2
        # 同じ PID であっても、マイクロ秒が違えば衝突しない。
        assert name1.endswith(f"_{os.getpid()}.log")
        assert name2.endswith(f"_{os.getpid()}.log")


class TestLoggingConflict:
    """他ライブラリの handler が root に混ざっているときの振る舞い。"""

    def test_setup_raises_logging_conflict_with_external_handler(
        self, isolated_logging, tmp_path, monkeypatch
    ):
        """外部ハンドラーがある状態で setup_logging() を呼ぶと LoggingConflictError。"""
        _prepare_site(monkeypatch, tmp_path)
        external = logging.StreamHandler()
        external.set_name("external.library")
        isolated_logging.addHandler(external)
        try:
            with pytest.raises(LoggingConflictError):
                setup_logging(Backoffice)
        finally:
            isolated_logging.removeHandler(external)
            external.close()

    def test_conflict_message_contains_handler_class_name(
        self, isolated_logging, tmp_path, monkeypatch
    ):
        """例外メッセージに既存ハンドラーのクラス名が含まれる。"""
        _prepare_site(monkeypatch, tmp_path)
        external = logging.StreamHandler()
        external.set_name("external.library")
        isolated_logging.addHandler(external)
        try:
            with pytest.raises(LoggingConflictError) as excinfo:
                setup_logging(Backoffice)
            assert "StreamHandler" in str(excinfo.value)
            assert "external.library" in str(excinfo.value)
        finally:
            isolated_logging.removeHandler(external)
            external.close()

    def test_conflict_message_contains_filehandler_path(
        self, isolated_logging, tmp_path, monkeypatch
    ):
        """FileHandler が混ざっている場合、出力先のパスがメッセージに含まれる。"""
        _prepare_site(monkeypatch, tmp_path)
        external_path = tmp_path / "external.log"
        external = logging.FileHandler(external_path, encoding="utf-8")
        external.set_name("external.library")
        isolated_logging.addHandler(external)
        try:
            with pytest.raises(LoggingConflictError) as excinfo:
                setup_logging(Backoffice)
            assert "FileHandler" in str(excinfo.value)
            assert str(external_path) in str(excinfo.value)
        finally:
            isolated_logging.removeHandler(external)
            external.close()

    def test_local_raises_logging_conflict_with_external_handler(self, isolated_logging):
        """外部ハンドラーがある状態で setup_local_logging() を呼んでも LoggingConflictError。"""
        external = logging.StreamHandler()
        external.set_name("external.library")
        isolated_logging.addHandler(external)
        try:
            with pytest.raises(LoggingConflictError):
                setup_local_logging()
        finally:
            isolated_logging.removeHandler(external)
            external.close()

    def test_local_conflict_message_contains_handler_info(self, isolated_logging):
        """setup_local_logging() でも例外メッセージに既存ハンドラーの情報が含まれる。"""
        external = logging.StreamHandler()
        external.set_name("external.library")
        isolated_logging.addHandler(external)
        try:
            with pytest.raises(LoggingConflictError) as excinfo:
                setup_local_logging()
            assert "StreamHandler" in str(excinfo.value)
            assert "external.library" in str(excinfo.value)
        finally:
            isolated_logging.removeHandler(external)
            external.close()

    def test_setup_allow_existing_proceeds_with_warning(self, tmp_path, monkeypatch):
        """allow_existing=True なら外部ハンドラーがあっても処理が続行し、警告ログが出る。

        ``isolated_logging`` を使うと ``root.handlers.clear()`` で他テスト用の
        handler も外れてしまうので、ここでは手動で root.handlers を退避・復元し、
        自前の ``CaptureHandler`` を一時的に root に追加してログを記録する。
        """
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers[:]
        original_level = root_logger.level
        root_logger.handlers.clear()
        external = logging.StreamHandler()
        external.set_name("external.library")
        capture = _LogCapture()
        capture.setLevel(logging.WARNING)
        try:
            _prepare_site(monkeypatch, tmp_path)
            root_logger.addHandler(external)
            root_logger.addHandler(capture)

            setup_logging(Backoffice, allow_existing=True)

            # comken の handler が両方追加されている
            assert {h.name for h in root_logger.handlers} >= {
                CONSOLE_HANDLER_NAME,
                ENVIRONMENT_HANDLER_NAME,
            }
            # 外部ハンドラーはそのまま残っている
            assert external in root_logger.handlers
            # 警告ログに記録されている
            warning_texts = [record.getMessage() for record in capture.records]
            assert any("allow_existing=True" in t for t in warning_texts)
            assert any("external.library" in t for t in warning_texts)
        finally:
            root_logger.handlers.clear()
            root_logger.handlers.extend(original_handlers)
            root_logger.setLevel(original_level)
            external.close()

    def test_local_allow_existing_proceeds_with_warning(self, tmp_path, monkeypatch):
        """setup_local_logging() でも allow_existing=True なら外部ハンドラーが
        あっても処理が続行し警告が出る。

        詳細は ``test_setup_allow_existing_proceeds_with_warning`` を参照。
        """
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers[:]
        original_level = root_logger.level
        root_logger.handlers.clear()
        external = logging.StreamHandler()
        external.set_name("external.library")
        capture = _LogCapture()
        capture.setLevel(logging.WARNING)
        try:
            self._prepare_setup_local_logging(monkeypatch, tmp_path)
            root_logger.addHandler(external)
            root_logger.addHandler(capture)

            setup_local_logging(allow_existing=True)

            assert {h.name for h in root_logger.handlers} >= {
                CONSOLE_HANDLER_NAME,
                LOCAL_HANDLER_NAME,
            }
            assert external in root_logger.handlers
            warning_texts = [record.getMessage() for record in capture.records]
            assert any("allow_existing=True" in t for t in warning_texts)
        finally:
            root_logger.handlers.clear()
            root_logger.handlers.extend(original_handlers)
            root_logger.setLevel(original_level)
            external.close()

    def test_setup_allow_existing_still_raises_when_already_called(
        self, isolated_logging, tmp_path, monkeypatch
    ):
        """allow_existing=True でも comken が1度呼ばれた状態では例外のまま。"""
        _prepare_site(monkeypatch, tmp_path)
        setup_logging(Backoffice)

        with pytest.raises(LoggingAlreadyConfiguredError):
            setup_logging(Backoffice, allow_existing=True)

    def test_local_allow_existing_still_raises_when_local_already_called(
        self, isolated_logging, tmp_path, monkeypatch
    ):
        """allow_existing=True でも setup_local_logging() を2回呼ぶと例外のまま。"""
        TestLocal()._prepare(monkeypatch, tmp_path)
        setup_local_logging()

        with pytest.raises(LoggingAlreadyConfiguredError):
            setup_local_logging(allow_existing=True)

    def test_conflict_message_mentions_allow_existing_workaround(
        self, isolated_logging, tmp_path, monkeypatch
    ):
        """LoggingConflictError のメッセージが ``allow_existing=True`` での共存手段に言及する。

        利用者が次に何をすればよいか分からないと現場で詰まるので、メッセージ内に
        エスケープハッチ (allow_existing=True) への言及があることを保証する。
        """
        _prepare_site(monkeypatch, tmp_path)
        external = logging.StreamHandler()
        external.set_name("external.library")
        isolated_logging.addHandler(external)
        try:
            with pytest.raises(LoggingConflictError) as excinfo:
                setup_logging(Backoffice)
            message = str(excinfo.value)
            assert "allow_existing=True" in message
        finally:
            isolated_logging.removeHandler(external)
            external.close()

    def test_conflict_message_tells_to_contact_admin(self, isolated_logging, tmp_path, monkeypatch):
        """LoggingConflictError のメッセージが「管理者へ連絡」する旨を含む。

        連絡先そのものは環境ごとに違うので書かないが、「管理者へ」が
        含まれていることを保証する（この例外は利用者コードでは解決しないため）。
        """
        _prepare_site(monkeypatch, tmp_path)
        external = logging.StreamHandler()
        external.set_name("external.library")
        isolated_logging.addHandler(external)
        try:
            with pytest.raises(LoggingConflictError) as excinfo:
                setup_logging(Backoffice)
            message = str(excinfo.value)
            assert "管理者" in message
        finally:
            isolated_logging.removeHandler(external)
            external.close()

    def test_format_external_handlers_emits_name_field_only_once(self):
        """_format_external_handlers() の各行で ``name=`` が1回しか現れない。

        旧実装では ``handler.name=None`` の StreamHandler に対して ``name=None`` と
        ``name=(未設定)`` が両方出ていた。名前が空のときの表記は handler の種類に
        よらず ``name=(未設定)`` に揃える（``set_name()`` を呼ばないライブラリが
        多く、``None`` がそのまま出ると読み手が戸惑うため）。``FileHandler`` は
        そのうえで ``path=`` を添える。
        """
        # StreamHandler / FileHandler は set_name を呼ばないと name は None のまま。
        stream_without_name = logging.StreamHandler()
        named_stream = logging.StreamHandler()
        named_stream.set_name("external.library")
        file_without_name = logging.FileHandler(os.devnull, encoding="utf-8")

        lines = _format_external_handlers([stream_without_name, named_stream, file_without_name])
        assert len(lines) == 3
        for line in lines:
            assert line.count("name=") == 1, line
        # 未設定の StreamHandler は日本語表記に統一されている。
        assert "name=(未設定)" in lines[0]
        assert "name=None" not in lines[0]
        # 名前付きはクォート付きで出る。
        assert "name='external.library'" in lines[1]
        # FileHandler も名前が空なら同じ表記。そのうえで出力先を添える。
        assert "name=(未設定)" in lines[2]
        assert "name=None" not in lines[2]
        assert "path=" in lines[2]

    def test_setup_allow_existing_writes_warning_to_comken_log_file(self, tmp_path, monkeypatch):
        """allow_existing=True のとき、警告が comken のログファイルに書かれている。

        警告が ``_guard_root_handlers()`` の中で出ていた旧実装では、警告時点では
        comken の FileHandler がまだ root に付いていないため、ログファイルへ
        記録されず「何と共存したか」追跡できなかった。修正後は comken の
        handler を root に追加し終えてから警告が出るので、ファイルに警告が
        残ること自体が順序の証左になる。
        """
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers[:]
        original_level = root_logger.level
        root_logger.handlers.clear()
        external = logging.StreamHandler()
        external.set_name("external.library")
        external_descriptions = _format_external_handlers([external])
        try:
            _prepare_site(monkeypatch, tmp_path)
            root_logger.addHandler(external)

            setup_logging(Backoffice, allow_existing=True)

            # comken のファイル handler を取得し、ファイルを読み込む。
            file_handler = next(
                h
                for h in root_logger.handlers
                if isinstance(h, logging.FileHandler) and h.name == ENVIRONMENT_HANDLER_NAME
            )
            file_handler.flush()
            text = Path(file_handler.baseFilename).read_text(encoding="utf-8")
            assert "WARNING" in text or "root logger に comken 以外" in text
            assert "allow_existing=True" in text
            assert "external.library" in text
            # ファイルに書かれた警告本文が、_format_external_handlers() の
            # 出力した行を含むことを確認（共食いではなく整合した内容が出ること）。
            for description in external_descriptions:
                assert description in text
        finally:
            root_logger.handlers.clear()
            root_logger.handlers.extend(original_handlers)
            root_logger.setLevel(original_level)
            external.close()

    def test_local_allow_existing_writes_warning_to_comken_log_file(self, tmp_path, monkeypatch):
        """setup_local_logging() でも allow_existing=True の警告が comken のログファイルに残る。"""
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers[:]
        original_level = root_logger.level
        root_logger.handlers.clear()
        external = logging.StreamHandler()
        external.set_name("external.library")
        external_descriptions = _format_external_handlers([external])
        try:
            self._prepare_setup_local_logging(monkeypatch, tmp_path)
            root_logger.addHandler(external)

            setup_local_logging(allow_existing=True)

            file_handler = next(
                h
                for h in root_logger.handlers
                if isinstance(h, logging.FileHandler) and h.name == LOCAL_HANDLER_NAME
            )
            file_handler.flush()
            text = Path(file_handler.baseFilename).read_text(encoding="utf-8")
            assert "allow_existing=True" in text
            assert "external.library" in text
            for description in external_descriptions:
                assert description in text
        finally:
            root_logger.handlers.clear()
            root_logger.handlers.extend(original_handlers)
            root_logger.setLevel(original_level)
            external.close()

    @staticmethod
    def _prepare_setup_local_logging(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """setup_local_logging() 用のテスト準備（TestLocal._prepare を流用）。"""
        logging.getLogger().handlers.clear()
        monkeypatch.setattr(sys, "argv", [str(tmp_path / "main.py")])
        monkeypatch.setattr(local_module, "today", lambda: _FIXED_TODAY)
        monkeypatch.setattr(
            "comken.core.logger.environment.today",
            lambda: _FIXED_TODAY,
        )
        monkeypatch.setattr(
            "comken.core.logger.environment.now",
            lambda: _FIXED_NOW,
        )
