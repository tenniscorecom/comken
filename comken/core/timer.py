"""comken/core/timer.py — 処理時間の計測

「どこが遅いのか／どこで止まったのか」を調べるためのユーティリティ。
with とデコレータの両方で使える。結果は logging に出る。
出力先・フォーマットは comken のログ設定（``setup_logging`` /
``setup_local_logging``）に従う。
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

# ログに出す文言の既定値。次のプレースホルダを使える。
#
# - ``{name}``: ``__init__`` の ``name``
# - ``{elapsed}``: ``time_format`` を ``str.format`` で整形した経過時間
#
# 経過時間の書式は ``message`` ではなく ``_TIME_FORMAT``（``time_format=``）
# の側で扱う。``message`` で使えるのは ``{name}`` と ``{elapsed}`` だけにし、
# 「文言」と「時間の整形」を役割で分ける。
#
# 呼び出し側で ``message=`` を渡すとこの文言を差し替えられる。
_MESSAGE = "{name}: {elapsed}"

# 経過時間の既定フォーマット。次のキーを ``str.format`` で参照する。
#
# - ``{hours}`` / ``{minutes}``: 経過時間を時・分に分けた int
#   （``hours`` は 24 を超えても繰り上げない）
# - ``{seconds}``: 経過秒数のうち時・分を引いた残り（**float**）。
#   秒未満を含むので、桁数は ``time_format`` 側のフォーマット指定で
#   決める（既定は ``{seconds:05.2f}`` で 2 桁）。
# - ``{total_seconds}``: 経過秒数の float（``self.elapsed`` そのもの）
#
# 表示の桁で丸めるため、59.996 秒のような値は ``"00:00:60.00"`` と
# 表示されることがあります（繰り上げはしません）。
#
# 例::
#
#     "{minutes}分{seconds:.1f}秒"
#     "{total_seconds:.2f}秒"
#
# 未知のキーは ``KeyError``。
_TIME_FORMAT = "{hours:02d}:{minutes:02d}:{seconds:05.2f}"


def _split_seconds(seconds: float) -> tuple[int, int, float]:
    """経過秒数を ``(時, 分, 秒)`` に分解する。

    ``hours`` / ``minutes`` は int（``hours`` は 24 を超えても繰り上げない）、
    ``seconds`` は **float**（秒未満を含む。例: 3661.7 秒 → ``(1, 1, 1.7)``）。
    秒未満の扱い（桁数・丸め）は ``time_format`` 側のフォーマット指定で
    決める（既定の ``_TIME_FORMAT`` は ``{seconds:05.2f}``）。
    """
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return int(hours), int(minutes), secs


def _format_elapsed(seconds: float, time_format: str) -> str:
    """経過秒数を ``time_format`` で文字列にする（``_split_seconds`` を内側で呼ぶ）。"""
    hours, minutes, secs = _split_seconds(seconds)
    return time_format.format(
        hours=hours,
        minutes=minutes,
        seconds=secs,
        total_seconds=seconds,
    )


class Timer:
    """処理時間を計測して INFO ログに出す。with・デコレータ両対応。

    Attributes:
        elapsed: 経過秒数（float）。with を抜けた後に参照できる。
    """

    def __init__(
        self,
        name: str = "処理",
        message: str = _MESSAGE,
        time_format: str = _TIME_FORMAT,
    ) -> None:
        """
        Args:
            name: ログに出す処理名（例: "CSV読み込み"）。
            message: ログに出す文言。次のプレースホルダを使える:

                - ``{name}``: ``__init__`` の ``name``
                - ``{elapsed}``: ``time_format`` で整形した経過時間

                例::

                    "{name} -> {elapsed}"

            time_format: 経過時間の整形書式。次のキーを ``str.format`` で
                参照する:

                - ``{hours}`` / ``{minutes}``: 経過時間を時・分に分けた
                  int（``hours`` は 24 を超えても繰り上げない）
                - ``{seconds}``: 経過秒数のうち時・分を引いた残りの
                  **float**（秒未満を含む）。桁数は ``time_format``
                  側のフォーマット指定で決める（例 ``"{seconds:.1f}"``）。
                - ``{total_seconds}``: 経過秒数の float
                  （``self.elapsed`` そのもの）

                例::

                    "{minutes}分{seconds:.1f}秒"
                    "{total_seconds:.2f}秒"

                未知のキーは ``KeyError``。

                ``{elapsed}`` の中身はこの ``time_format`` で決まる。
        """
        self._name = name
        self._message = message
        self._time_format = time_format
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
        logger.info(
            "%s",
            self._message.format(
                name=self._name,
                elapsed=_format_elapsed(self.elapsed, self._time_format),
            ),
        )

    def __call__(self, func: Callable[_P, _R]) -> Callable[_P, _R]:
        """デコレータとして使う（@Timer("処理名")）。"""

        @functools.wraps(func)
        def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            """呼び出しごとに独立したTimerで処理時間を測る。"""
            # 呼び出しごとに独立して計測する（同じ Timer を使い回さない）。
            # message / time_format も一緒に引き継ぐ（忘れると差し替えが効かない）
            with Timer(self._name, self._message, self._time_format):
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


def _measure_wrapper[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """通常関数用の ``measure`` ラッパーを組み立てる。"""

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
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


def measure[**P, R](func: Callable[P, R]) -> Callable[P, R]:
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
