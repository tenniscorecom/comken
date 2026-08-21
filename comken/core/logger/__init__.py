"""社内環境用および単体実行用のログ設定。"""

import logging
from pathlib import Path

from comken.core.logger._env import setup_environment_logging
from comken.core.logger._local import setup_local_logging
from comken.core.logger._site import Backoffice, Intranet, LoggerSite

DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR

__all__ = [
    "Backoffice",
    "Intranet",
    "setup_logging",
    "local",
    "DEBUG",
    "INFO",
    "WARNING",
    "ERROR",
]


def setup_logging(site: type[LoggerSite]) -> None:
    """指定した社内環境向けに root logger を設定する。"""
    setup_environment_logging(site)


def setup(site: type[LoggerSite]) -> None:
    """``setup_logging`` のモジュール利用向け短縮名。"""
    setup_logging(site)


def local(
    *,
    console_level: int = INFO,
    file_level: int = INFO,
    path: str | Path | None = None,
) -> logging.Logger:
    """単体実行用 logger を作成して返す。複数回の呼び出しも許可する。"""
    return setup_local_logging(
        console_level=console_level,
        file_level=file_level,
        path=path,
    )
