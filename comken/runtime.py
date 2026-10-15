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
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from comken.exceptions import ComkenError

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


def dry_run_log(action: str, *args: object) -> None:
    """dry-run でスキップした操作をログに出す（ライブラリ内部用）。"""
    logger.info("[DRY-RUN] %s", action % args if args else action)


def run_main(
    main: Callable[[], int | None],
    *,
    debug_mode: bool = False,
    dry_run_mode: bool = False,
) -> int:
    """``main()`` を dry-run / debug の有無で囲んで呼び出し、終了コードを返す。

    4 リポジトリの ``main.py`` に同形だった次のセットを 1 か所にまとめる:

    - ``comken_logger.setup_local_logging()`` を前提とする（``main.py`` 側で 1 回呼ぶ）
    - ``with dry_run():`` / ``with debug():`` を ``debug_mode`` / ``dry_run_mode`` で切り替え
    - ``main()`` の戻り値が ``int`` ならそのまま、``None`` なら 0
    - ``ComkenError`` のときは ``logger.error("処理を中断しました: %s", e)`` を出した上で 1
    - 想定外の例外は ``logger.exception(...)`` した上で **そのまま再送出** する
      （RPA 基盤／スケジューラが受け取れるように）

    新しい状態を持たず、既存の ``with dry_run():`` / ``with debug():`` の
    仕組みをそのまま使う。``main`` の内部で ``is_dry_run()`` / ``is_debug()``
    が True になるかどうかは、``debug_mode`` / ``dry_run_mode`` 引数どおり。

    典型的な ``main.py``::

        from comken import comken_logger
        from comken.runtime import run_main
        from src.run import run

        def main() -> int:
            return run()

        if __name__ == "__main__":
            comken_logger.setup_local_logging()
            raise SystemExit(run_main(main))

    Args:
        main: 実行する処理。戻り値は ``int``（終了コード）か ``None``。
        debug_mode: True なら呼び出し中だけ ``with debug():`` で囲む。
        dry_run_mode: True なら呼び出し中だけ ``with dry_run():`` で囲む。

    Returns:
        ``main()`` の戻り値（``int``）か、``None`` のときの ``0``。
        ``ComkenError`` で止まったときは ``1``。
    """
    if debug_mode and dry_run_mode:
        with debug(), dry_run():
            return _invoke_main(main)
    if debug_mode:
        with debug():
            return _invoke_main(main)
    if dry_run_mode:
        with dry_run():
            return _invoke_main(main)
    return _invoke_main(main)


def _invoke_main(main: Callable[[], int | None]) -> int:
    """``run_main`` の本体。``with`` を一段減らして表を見やすくする内部用ヘルパー。"""
    try:
        result = main()
    except ComkenError as e:
        # comken の例外メッセージには対処法が含まれている（docs/ERRORS.md も参照）。
        logger.error("処理を中断しました: %s", e)
        return 1
    except Exception:
        # 想定外は RPA 基盤／スケジューラに届くよう、ログだけ残して再送出する
        logger.exception("予期しないエラーが発生しました")
        raise
    return 0 if result is None else int(result)
