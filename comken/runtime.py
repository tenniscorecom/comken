"""
runtime.py — ライブラリ全体の実行モード（デバッグ・dry-run）

使い方:
    import comken

    comken.__version__        # → "0.2.0"（ライブラリのバージョン）

    # デバッグモード: ライブラリ主要処理の所要時間が DEBUG ログに残る
    # （setup_logger を使っていれば日別ログファイルに出る。コンソールには出ない）
    comken.set_debug(True)

    # dry-run モード: 外部に影響する操作を実行せず、内容だけ INFO ログに出す
    # 対象: ファイルの移動・コピー、Excel/CSV の保存
    comken.set_dry_run(True)
"""

import logging

logger = logging.getLogger(__name__)

_debug = False
_dry_run = False


def set_debug(enabled: bool = True) -> None:
    """デバッグモードを切り替える。

    有効にすると、ライブラリの主要処理（Excel 読み込み・転記・保存、CSV 読み書き、
    zip 等）の所要時間が DEBUG ログに記録される。どこが遅いかの調査に使う。

    Args:
        enabled: True で有効（デフォルト）。False で無効。
    """
    global _debug
    _debug = enabled
    logger.info("デバッグモード: %s", "ON（処理時間を DEBUG ログに記録）" if enabled else "OFF")


def is_debug() -> bool:
    """デバッグモードが有効か返す。"""
    return _debug


def set_dry_run(enabled: bool = True) -> None:
    """dry-run モードを切り替える。

    有効にすると、外部に影響する操作を実行せず、何をするはずだったかを
    INFO ログ（[DRY-RUN] プレフィックス付き）に出す。本番実行前の動作確認に使う。

    対象の操作:
        - move_file / copy_file（ファイルの移動・コピー）
        - ExcelFile.save / CsvWriter の書き込み

    読み取り（CSV・Excel の読み込み、SOQL クエリ等）は通常どおり実行される。

    Args:
        enabled: True で有効（デフォルト）。False で無効。
    """
    global _dry_run
    _dry_run = enabled
    logger.info("dry-run モード: %s", "ON（外部に影響する操作をスキップ）" if enabled else "OFF")


def is_dry_run() -> bool:
    """dry-run モードが有効か返す。"""
    return _dry_run


def dry_run_log(action: str, *args) -> None:
    """dry-run でスキップした操作をログに出す（ライブラリ内部用）。"""
    logger.info("[DRY-RUN] " + action, *args)
