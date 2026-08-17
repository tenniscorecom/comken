"""comken/core/timer.py — 処理時間の計測

「どこが遅いのか／どこで止まったのか」を調べるためのユーティリティ。
with とデコレータの両方で使える。結果は logging に出る。
出力先・フォーマット・レベルは社内の共通ライブラリ側で設定する。
"""

# 定義中の Timer を戻り値の型注釈に使うため、注釈の評価を遅延する。
from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from typing import ParamSpec, Self, TypeVar

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

    def __enter__(self) -> Self:
        # NOTE: 経過時間の計測であり、現在の日時の取得ではない。
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args) -> None:
        self.elapsed = time.perf_counter() - self._start
        logger.info("%s: %.2f秒", self._name, self.elapsed)

    def __call__(self, func: Callable[_P, _R]) -> Callable[_P, _R]:
        """デコレータとして使う（@Timer("処理名")）。"""

        @functools.wraps(func)
        def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            """呼び出しごとに独立したTimerで処理時間を測る。"""
            # 呼び出しごとに独立して計測する（同じ Timer を使い回さない）
            with Timer(self._name):
                return func(*args, **kwargs)

        return wrapper


def measure(func: Callable[_P, _R]) -> Callable[_P, _R]:
    """デバッグモード時だけ対象関数の出入りを DEBUG ログに出すデコレータ。

    呼び出しごとに次の3種のうち、いずれか1組を出す:

    - 開始
    - 完了 ○.○○○秒        （正常終了）
    - 中断 ○.○○○秒        （例外で抜けた場合。BaseException も拾う）

    **「開始」を必ず出してから本体を呼ぶ。** 処理が外部待ちで止まったとき、
    ログの末尾が「開始」で終わっていれば、そこが停止位置だと分かる。
    終了時にしかログを出さないと、止まった処理の記録は永久に残らない。

    **引数・戻り値はログに出さない。** comken は DPAPI のトークン・client_secret・
    パスワードを扱うため、汎用デコレータが自動で引数を出せる形になっていると、
    いつか秘密の値がログへ載る危険がある。「どのメソッドで止まったか」までは
    ライブラリが受け持ち、「どのファイル・どの行で止まったか」は呼び出し側が
    処理対象を DEBUG ログへ出す形にする。

    例外は `BaseException` で捕捉し、`raise` で必ず再送出する
    （`KeyboardInterrupt` も拾う。ハングして Ctrl+C で止めたときに
    「どこで待っていたか」が分かるのが狙い）。

    Timer との使い分け:
        - Timer: 常にログに出したい・経過秒数を値として使いたい場合
        - measure: 普段は出さず、調査のときだけ with debug(): で出したい場合
    """

    @functools.wraps(func)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        """デバッグ中だけ対象関数の出入りを記録する。"""
        from comken.runtime import is_debug

        if not is_debug():
            return func(*args, **kwargs)

        # 関数名（qualname）だけ。引数・戻り値は出さない（理由は docstring 参照）
        name = func.__qualname__
        logger.debug("%s: 開始", name)
        start = time.perf_counter()
        try:
            # try の中で直接 return すると else 節が走らないので、
            # 変数に受けて try の外で return する
            result = func(*args, **kwargs)
        except BaseException:
            # KeyboardInterrupt も拾う。中断位置が「開始」の直後で分かるので
            # ハング時の調査になる。握りつぶさず必ず再送出する
            logger.debug("%s: 中断 %.3f秒", name, time.perf_counter() - start)
            raise
        else:
            logger.debug("%s: 完了 %.3f秒", name, time.perf_counter() - start)
        return result

    return wrapper
