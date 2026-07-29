"""
utils/timer.py — 処理時間の計測

「どこが遅いのか」を調べるためのユーティリティ。with とデコレータの両方で使える。
結果は logging（INFO）に出る。出力先・フォーマット・レベルは社内の共通ライブラリ側で設定する。

使い方:
    from comken.utils import Timer

    # with で区間を計測する
    with Timer("CSV読み込み"):
        rows = CsvReader("data.csv").rows()
    # ログ: CSV読み込み: 3.21秒

    # デコレータで関数全体を計測する
    @Timer("売上集計")
    def aggregate():
        ...

    # 経過秒数を値として使う
    t = Timer("転記処理")
    with t:
        ...
    if t.elapsed > 60:
        notifier.send(f"転記処理が {t.elapsed:.0f} 秒かかっています")
"""

import functools
import logging
import time
from typing import Callable, ParamSpec, TypeVar

logger = logging.getLogger(__name__)

_P = ParamSpec("_P")
_R = TypeVar("_R")


class Timer:
    """処理時間を計測して INFO ログに出す。with・デコレータ両対応。

    Attributes:
        elapsed: 経過秒数（float）。with を抜けた後に参照できる。
    """

    def __init__(self, name: str = "処理") -> None:
        """
        Args:
            name: ログに出す処理名（例: "CSV読み込み"）。
        """
        self._name = name
        self._start = 0.0
        self.elapsed = 0.0

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args) -> None:
        self.elapsed = time.perf_counter() - self._start
        logger.info("%s: %.2f秒", self._name, self.elapsed)

    def __call__(self, func: Callable[_P, _R]) -> Callable[_P, _R]:
        """デコレータとして使う（@Timer("処理名")）。"""

        @functools.wraps(func)
        def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            # 呼び出しごとに独立して計測する（同じ Timer を使い回さない）
            with Timer(self._name):
                return func(*args, **kwargs)

        return wrapper


def measure(func: Callable[_P, _R]) -> Callable[_P, _R]:
    """デバッグモード時だけ処理時間を DEBUG ログに出すデコレータ。

    ライブラリの主要処理に付いており、with comken.debug(): の範囲では
    「どの処理に何秒かかったか」を DEBUG ログに出す。
    プロジェクト側の関数に付けてもよい。

    Timer との使い分け:
        - Timer: 常にログに出したい・経過秒数を値として使いたい場合
        - measure: 普段は出さず、調査のときだけ with debug(): で出したい場合

    使い方:
        from comken.utils import measure

        @measure
        def build_report():
            ...
    """

    @functools.wraps(func)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        from ..runtime import is_debug

        if not is_debug():
            return func(*args, **kwargs)
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            logger.debug("%s: %.3f秒", func.__qualname__, time.perf_counter() - start)

    return wrapper
