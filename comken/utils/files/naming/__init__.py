"""comken/utils/files/naming/__init__.py — 命名方法を1ファイル1方式で追加する場所。

日付以外の方式を足すときは、このパッケージに新しいモジュールを作る。
"""

from .date import DateNameBuilder

__all__ = ["DateNameBuilder"]
