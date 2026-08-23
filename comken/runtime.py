"""comken/runtime.py — ライブラリ全体の実行モード（デバッグ・dry-run）

dry-run モードとデバッグモードの管理。

`is_dry_run()` / `is_debug()` の戻り値は、次の順で決定される:

1. プロセスの状態（`with dry_run():` / `with debug():` のブロック内なら True）
2. 既定値 False

`config.ini` も環境変数も setter も読まない。**コード上の `with` ブロックで
切り替える**のが唯一の方法。

`is_dry_run()` / `is_debug()` は **内部用** であり、`comken` の facade には
載せていない（→ `comken/__init__.py`）。`delete_file` などの dry-run 対応
関数が dry-run 中か判定するために呼ぶ。公開 API ではないので、利用者が
直接呼ぶ必要はない。
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# 内部状態。`with dry_run():` / `with debug():` の context manager が切り替える。
_dry_run: bool = False
_debug: bool = False


def is_dry_run() -> bool:
    """dry-run モードが有効か返す（内部用）。

    `with dry_run():` のブロック内で True、それ以外では False。
    `delete_file` などの dry-run 対応関数が dry-run 中か判定するために呼ぶ。
    """
    return _dry_run


def is_debug() -> bool:
    """デバッグモードが有効か返す（内部用）。

    `with debug():` のブロック内で True、それ以外では False。
    """
    return _debug


@contextmanager
def dry_run(enabled: bool = True) -> Iterator[None]:
    """ブロック内だけ dry-run モードにする。

    Args:
        enabled: True で有効（デフォルト）。False ならブロック内だけ無効。
    """
    global _dry_run
    previous = _dry_run
    _dry_run = enabled
    try:
        yield
    finally:
        _dry_run = previous


@contextmanager
def debug(enabled: bool = True) -> Iterator[None]:
    """ブロック内だけデバッグモードにする。

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


def dry_run_log(action: str, *args) -> None:
    """dry-run でスキップした操作をログに出す（ライブラリ内部用）。"""
    logger.info("[DRY-RUN] %s", action % args if args else action)
