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
import re
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
# - ``{elapsed}``: ``time_format`` で整形した経過時間
#
# 経過時間の書式は ``message`` ではなく ``time_format`` の側で扱う。
# ``message`` で使えるのは ``{name}`` と ``{elapsed}`` だけにし、
# 「文言」と「時間の整形」を役割で分ける。
#
# 呼び出し側で ``message=`` を渡すとこの文言を差し替えられる。
_MESSAGE = "{name}: {elapsed}"

# 経過時間の既定フォーマット。``None`` のときは下の ``_DEFAULT_FORMAT_ELAPSED``
# （``"{total_seconds:.2f}秒"`` 相当）で出す。秒未満をそのまま残し、
# 「0.30秒」のように単位つきの形でログへ載せる形。
_TIME_FORMAT: str | None = None

# ``time_format=None`` のときに適用する既定の表示。 ``str.format`` で
# 経過秒数を小数2桁で出す。 ``{total_seconds}`` のキーは外部仕様ではなく
# 内部実装（``_format_elapsed`` の第2分岐）にだけ存在するため、利用側は
#  ``time_format=None`` と ``time_format="hh:mm:ss"`` を切り替えれば十分。
_DEFAULT_FORMAT_ELAPSED = "{total_seconds:.2f}秒"

# ``hh`` / ``mm`` / ``ss`` の3つだけを許す ``time_format`` のパターン。
# 大文字小文字は区別しない（re.IGNORECASE）。
# 一致した ``hh`` / ``mm`` / ``ss`` は、その位置の前後を残したまま
# 経過時・分・秒に置き換える（str.format のキーではないので、``hh:mm:ss``
# のような固定文字列にそのまま埋め込める）。
_TIME_PLACEHOLDER_RE = re.compile("hh|mm|ss", re.IGNORECASE)


def _split_seconds(seconds: float) -> tuple[int, int, int]:
    """経過秒数を ``(時, 分, 秒)`` に分解する（すべて整数）。

    経過秒は **切り捨て**て整数秒にする（四捨五入しない）。
    ``hh:mm:ss`` 形式の ``time_format`` で 59.6 秒が ``00:00:60`` と
    表示される問題をなくすための仕様。 ``hours`` は 24 を超えても
    繰り上げない（``hh`` 部分の桁が増えるだけ）。

    ``time_format`` の ``hh`` / ``mm`` / ``ss`` 置換で直接使う値。
    """
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return hours, minutes, secs


def _format_elapsed(seconds: float, time_format: str | None) -> str:
    """経過秒数を ``time_format`` で文字列にする。

    ``time_format`` が ``None`` のときは ``_DEFAULT_FORMAT_ELAPSED``
    （小数2桁＋「秒」）で返す。文字列のときはその中の ``hh`` / ``mm`` / ``ss``
    （大文字小文字区別なし）を経過時・分・秒に置き換え、それ以外はそのまま返す。
    ``hh`` / ``mm`` / ``ss`` のいずれも含まれない文字列は、
    ``time_format`` が無視される事故を防ぐため ``__init__`` で ``ValueError``
    にしてある（この関数が直接呼ばれる場合は呼び出し側の責務）。
    """
    if time_format is None:
        # ``_TIME_FORMAT`` の既定値。``{total_seconds:.2f}秒`` の形にする。
        return _DEFAULT_FORMAT_ELAPSED.format(total_seconds=seconds)
    hours, minutes, secs = _split_seconds(seconds)
    return _TIME_PLACEHOLDER_RE.sub(
        lambda m: {"hh": f"{hours:02d}", "mm": f"{minutes:02d}", "ss": f"{secs:02d}"}[
            m.group(0).lower()
        ],
        time_format,
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
        time_format: str | None = _TIME_FORMAT,
    ) -> None:
        """
        Args:
            name: ログに出す処理名（例: "CSV読み込み"）。
            message: ログに出す文言。次のプレースホルダを使える:

                - ``{name}``: ``__init__`` の ``name``
                - ``{elapsed}``: ``time_format`` で整形した経過時間

                例::

                    "{name} -> {elapsed}"

            time_format: 経過時間の整形書式。

                - ``None``（既定）: 小数2桁＋「秒」（例 ``"3.21秒"``）
                - 文字列: その中の ``hh`` / ``mm`` / ``ss`` を経過時間で
                  置き換える。大文字小文字は区別しない（``HH:MM:SS`` も同じ）。

                  経過秒は **整数秒に切り捨て**てから時・分・秒に分解する
                  （四捨五入しない。59.6 秒が ``00:00:60`` と表示される問題を
                  なくすため）。

                  - ``hh`` = 時（24 を超えても繰り上げない。100 時間超なら
                    桁が増える）
                  - ``mm`` = 時を引いた残りの分
                  - ``ss`` = 分を引いた残りの秒

                  それぞれ2桁ゼロ埋め。

                  例::

                      "hh:mm:ss"        # → "01:02:05"
                      "HH:MM:SS"        # 大文字小文字どちらでも同じ
                      "mm分ss秒"        # 3725 秒 → "02分05秒"（mm は時を引いた残り）
                      "hh時間mm分ss秒"

                ``hh`` / ``mm`` / ``ss`` の **どれも** 含まない文字列は
                ``ValueError`` にする（``hh`` なしの ``"h:m:s"`` や
                ``"{hours:02d}"`` のような旧 ``str.format`` キーが来ても、
                黙って意味の違う表示にしないため）。

                ``{elapsed}`` の中身はこの ``time_format`` で決まる。
        """
        if time_format is not None and not _TIME_PLACEHOLDER_RE.search(time_format):
            raise ValueError(
                "time_format には hh / mm / ss のいずれかを含めてください。"
                ' 例: "hh:mm:ss"、"mm分ss秒"。'
                f" 受け取った書式: {time_format!r}"
            )
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
