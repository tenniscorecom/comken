"""comken/core/retry.py — リトライデコレータ

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
        on: リトライ対象の例外のタプル（デフォルト: すべての Exception 系）。
            ``Exception`` のサブクラスを指定する。**``BaseException`` 系
            （``KeyboardInterrupt`` / ``SystemExit``）は ``on`` に含まれていても
            リトライしない**（Ctrl+C で止められることを保証するため）。
            ``on`` に含まれない例外は即座にそのまま出る。

    Raises:
        ValueError: times が正の整数でない、または wait が負の値。
        最後の実行で出た例外（times 回すべて失敗した場合）。

    Note:
        入力値検証で ``ValueError`` を投げる。``times`` を 0 以下にしたいケースは
        ループ自体を不要としているので、黙って 1 にするのではなく例外で知らせる
        （誤って ``times=None`` を渡して 1 回しか実行されない事故を防ぐ）。
    """

    # ── 入力値検証 ────────────────────────────────────────────────────────────
    # ここで検査して例外を投げるのは「ランタイムで繰り返し実行する関数」が
    # 想定と違うパラメータで動かないようにするため。silent な max(1) は避け、
    # 期待と違う設定は明示的に失敗させる。
    if not isinstance(times, int) or isinstance(times, bool) or times < 1:
        raise ValueError(f"times は 1 以上の整数で指定してください (got {times!r})")
    if wait < 0:
        raise ValueError(f"wait は 0 以上で指定してください (got {wait!r})")

    total = times
    retry_targets: tuple[type[BaseException], ...] = tuple(on)

    def decorator(func: Callable[_P, _R]) -> Callable[_P, _R]:
        """対象関数へ再実行処理を適用する。"""

        @functools.wraps(func)
        def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            """指定回数まで対象関数を再実行する。"""
            for attempt in range(1, total + 1):
                try:
                    return func(*args, **kwargs)
                except BaseException as e:
                    # BaseException 系（KeyboardInterrupt / SystemExit）は
                    # リトライしない。on に含まれていても、ユーザーの
                    # 「今ここで止めたい」を尊重する。
                    # isinstance(e, BaseException) は常に True なので
                    # isinstance(e, Exception) が False = BaseException 直系
                    if not isinstance(e, Exception):
                        raise
                    # on に含まれない例外もリトライしない
                    if not isinstance(e, retry_targets):
                        raise
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
