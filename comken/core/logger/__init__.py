"""comken/core/logger/__init__.py — 社内環境用および単体実行用のログ設定。

社内環境では ``setup(Backoffice)`` のように root logger を設定する。単体実行では
``local()`` で root logger を設定する。薄いラッパーを作らず実装を直接再公開するため、
署名・docstring・例外発生箇所が利用者から見ても実装と一致する。
"""

import logging

from comken.core.logger.environment import setup
from comken.core.logger.local import local
from comken.core.logger.site import Backoffice, Intranet

DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR
getLogger = logging.getLogger

__all__ = [
    "Backoffice",
    "Intranet",
    "setup",
    "local",
    "DEBUG",
    "INFO",
    "WARNING",
    "ERROR",
    "getLogger",
]
