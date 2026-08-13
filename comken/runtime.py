"""
runtime.py — ライブラリ全体の実行モード（デバッグ・dry-run）

"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_debug = False
_dry_run = False


@contextmanager
def debug(enabled: bool = True) -> Iterator[None]:
    """ブロック内だけデバッグモードを指定した状態にする。

    有効にすると、ライブラリの主要処理（Excel 読み込み・転記・保存、CSV 読み書き、
    zip 等）の所要時間が DEBUG ログに記録される。どこが遅いかの調査に使う。

    Args:
        enabled: True で有効（デフォルト）。False ならブロック内だけ無効。
    """
    global _debug
    previous = _debug
    _debug = enabled
    try:
        yield
    finally:
        _debug = previous


def is_debug() -> bool:
    """デバッグモードが有効か返す。"""
    return _debug


@contextmanager
def dry_run(enabled: bool = True) -> Iterator[None]:
    """ブロック内だけ dry-run モードを指定した状態にする。

    有効にすると、外部に影響する操作を実行せず、何をするはずだったかを
    INFO ログ（[DRY-RUN] プレフィックス付き）に出す。本番実行前の動作確認に使う。

    対象の操作:
        - move_file / copy_file（ファイルの移動・コピー）
        - ExcelWriter.save / CsvWriter の書き込み
        - State.set（state.ini の書き込み）

    読み取り（CSV・Excel の読み込み、SOQL クエリ等）は通常どおり実行される。

    Args:
        enabled: True で有効（デフォルト）。False ならブロック内だけ無効。
                 外側が dry-run 中でも、このブロックでは通常どおり書き込む。
    """
    global _dry_run
    previous = _dry_run
    _dry_run = enabled
    try:
        yield
    finally:
        _dry_run = previous


def is_dry_run() -> bool:
    """dry-run モードが有効か返す。"""
    return _dry_run


def dry_run_log(action: str, *args) -> None:
    """dry-run でスキップした操作をログに出す（ライブラリ内部用）。"""
    logger.info("[DRY-RUN] %s", action % args if args else action)
