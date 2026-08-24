"""comken/core/logger/__init__.py — 社内環境用および単体実行用のログ設定。

社内環境では ``setup_logging(Backoffice)`` のように root logger を設定する。
単体実行では ``setup_local_logging()`` で root logger を設定する。
薄いラッパーを作らず実装を直接再公開するため、署名・docstring・例外発生箇所が
利用者から見ても実装と一致する。
"""

from comken.core.logger.environment import setup_logging
from comken.core.logger.local import setup_local_logging
from comken.core.logger.site import Backoffice, Intranet

__all__ = [
    "Backoffice",
    "Intranet",
    "setup_logging",
    "setup_local_logging",
]
