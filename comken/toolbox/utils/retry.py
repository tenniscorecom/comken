"""comken/toolbox/utils/retry.py — リトライデコレータ

一時的な失敗（クリックが要素に遮られた、ネットワークが一瞬切れた等）を
自動でやり直すためのデコレータ。
"""

import functools
import logging
import time
from collections.abc import Callable
from typing import ParamSpec, TypeVar

logger = logging.getLogger(__name__)

_P = ParamSpec("_P")
_R = TypeVar("_R")


def retry(
    times: int = 3, wait: float = 1.0, on: tuple = (Exception,)
) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    """失敗したら wait 秒空けて実行し直すデコレータ。

    Args:
        times: 合計の実行回数（デフォルト: 3。「3回試して全部失敗ならエラー」）。
        wait: 失敗から次の実行までの待機秒数（デフォルト: 1秒）。
        on: リトライ対象の例外のタプル（デフォルト: すべての例外）。
            ここに含まれない例外は即座にそのまま出る。

    Raises:
        最後の実行で出た例外（times 回すべて失敗した場合）。
    """

    # times=0 以下でも最低1回は実行する（None を黙って返さないため）
    total = max(int(times), 1)

    def decorator(func: Callable[_P, _R]) -> Callable[_P, _R]:
        """対象関数へ再実行処理を適用する。"""

        @functools.wraps(func)
        def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            """指定回数まで対象関数を再実行する。"""
            for attempt in range(1, total + 1):
                try:
                    return func(*args, **kwargs)
                except on as e:
                    if attempt == total:
                        raise
                    logger.warning(
                        "%s が失敗しました（%d/%d回目）。%s秒後に再実行します: %s",
                        func.__name__,
                        attempt,
                        total,
                        wait,
                        e,
                    )
                    time.sleep(wait)
            # ここには到達しない（total>=1 で必ず return か raise する）が、
            # 型チェッカーに「None を返さない」ことを保証する
            raise AssertionError("retry: 到達不能")

        return wrapper

    return decorator
