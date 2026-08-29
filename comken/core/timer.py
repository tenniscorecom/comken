"""comken/core/timer.py — 処理時間の計測

「どこが遅いのか／どこで止まったのか」を調べるためのユーティリティ。
with とデコレータの両方で使える。結果は logging に出る。
出力先・フォーマット・レベルは社内の共通ライブラリ側で設定する。
"""

# 定義中の Timer を戻り値の型注釈に使うため、注釈の評価を遅延する。
from __future__ import annotations

import functools
import inspect
import logging
import time
from collections.abc import Callable
from types import TracebackType
from typing import Any, ParamSpec, Self, TypeVar

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

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
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


def _measure_generator_wrapper(func: Callable[..., Any]) -> Callable[..., Any]:
    """ジェネレータ関数用の ``measure`` ラッパーを組み立てる。"""

    def generator_wrapper(*args: Any, **kwargs: Any) -> Any:
        """ジェネレータ関数に measure を付けたとき用の薄いラッパー。

        ``func(*args, **kwargs)`` はジェネレータオブジェクトを返すだけで、
        本体の ``yield`` は ``next()`` が呼ばれてから走る。 呼び出した
        だけで完了ログが出る事故を防ぐため、本体を包んだジェネレータを返し、
        最初の ``next()`` で開始ログ、消費し切ったら完了ログ、
        例外・``GeneratorExit`` で抜けたら中断ログを出す。

        **「開始」を ``next()`` で本体を呼ぶより前**に出す。 ``query_rows``
        のように最初の ``yield`` より前に時間のかかる処理を入れる書き方が
        あるため、 本体の前段を「開始→完了」の計測範囲から外さない。
        本体が ``next()`` の直後にハングした場合も「開始」ログは既に出ているので、
        ログの末尾が「開始」で終わっていれば停止位置が分かる。
        """
        from comken.runtime import is_debug

        # デバッグ無効時は素通し。 ``yield from`` で内側ジェネレータの値を
        # そのまま外へ流し、 呼び出し側の ``next()`` が無用に増えるのを避ける
        if not is_debug():
            yield from func(*args, **kwargs)
            return

        name = func.__qualname__
        # NOTE: 開始ログと start_time は「最初の ``next()`` を呼ぶ前」に出す。
        # 計測範囲に内側ジェネレータの先頭処理（最初の ``yield`` までの全処理）を
        # 含めるためで、 ハング時に「開始」ログが出ていることを保証するためでもある。
        start_time = time.perf_counter()
        logger.debug("%s: 開始", name)
        inner = func(*args, **kwargs)
        # 外側ラッパー最初の ``next()`` で inner の本体を開始させる。
        # 開始ログと start_time は外側で既に出しているので、ここで再度出さない。
        try:
            value = next(inner)
        except StopIteration:
            # 本体が yield を一度も呼ばずに終わった（空ジェネレータ）
            logger.debug("%s: 完了 %.3f秒", name, time.perf_counter() - start_time)
            return
        except BaseException:
            # next() で例外が上がった = 本体開始直後の失敗
            logger.debug("%s: 中断 %.3f秒", name, time.perf_counter() - start_time)
            raise
        while True:
            try:
                received = yield value
            except GeneratorExit:
                inner.close()
                logger.debug("%s: 中断 %.3f秒", name, time.perf_counter() - start_time)
                raise
            except BaseException:
                logger.debug("%s: 中断 %.3f秒", name, time.perf_counter() - start_time)
                raise
            try:
                value = inner.send(received)
            except StopIteration:
                logger.debug("%s: 完了 %.3f秒", name, time.perf_counter() - start_time)
                return
            except BaseException:
                logger.debug("%s: 中断 %.3f秒", name, time.perf_counter() - start_time)
                raise

    # ``functools.wraps`` は関数本体がジェネレータ関数の場合に警告されるので、
    # 属性だけ手動でコピーする
    functools.wraps(func)(generator_wrapper)
    return generator_wrapper


def _measure_wrapper(func: Callable[_P, _R]) -> Callable[_P, _R]:
    """通常関数用の ``measure`` ラッパーを組み立てる。"""

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

    ジェネレータ関数に付けた場合は、本体が `next()` で評価され始めるまで
    「開始」を出さない（呼び出しただけで完了ログが出る事故を防ぐ）。専用の
    ラッパーがジェネレータを返し、最初の `next()` で開始、消費し切ったら完了、
    例外や `GeneratorExit` で抜けたら中断を出す。

    Timer との使い分け:
        - Timer: 常にログに出したい・経過秒数を値として使いたい場合
        - measure: 普段は出さず、調査のときだけ with debug(): で出したい場合
    """
    if inspect.isgeneratorfunction(func):
        return _measure_generator_wrapper(func)
    return _measure_wrapper(func)
