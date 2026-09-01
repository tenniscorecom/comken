"""comken/core/runner.py — 「開始をログに出してから呼ぶ」の共通処理。

``comken.internal.rpa`` のように、外部の入口を1つ呼ぶだけの処理でも
「呼ぶ前に開始をログへ出す」は毎回同じ形になる。ここに土台を1つ置き、
呼び出し側はログに出す名前と処理本体だけ渡す。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

_R = TypeVar("_R")


def run(label: str, func: Callable[[], _R]) -> _R:
    """``label`` を開始ログに出してから ``func()`` を呼ぶ。

    Args:
        label: ログに出す処理名（例: ``"backoffice で 受注取込"``）。
        func: 実行する処理（引数無しの callable）。引数を渡したい場合は
            呼び出し側で ``lambda`` に束縛してから渡す。

    Returns:
        ``func()`` の戻り値。
    """
    logger.info("%s を開始します", label)
    return func()


__all__ = ["run"]
