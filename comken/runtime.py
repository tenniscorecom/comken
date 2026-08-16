"""comken/runtime.py — ライブラリ全体の実行モード（デバッグ・dry-run）"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_debug = False
_dry_run = False


@contextmanager
def debug(enabled: bool = True) -> Iterator[None]:
    """ブロック内だけデバッグモードを指定した状態にする。

    有効にすると、`@measure` を付けたメソッドの出入りを DEBUG ログに記録する。
    ログは関数ごとに次の2行（例外時は別の1行）になる:

        DEBUG ExcelWriter.save: 開始
        DEBUG ExcelWriter.save: 完了 1.234秒

    **主目的は「どの処理で止まったか」を後から特定できるようにすること。**
    業務バッチが外部待ち（ブラウザ・HTTP・Excel COM・共有サーバー）で止まったとき、
    ログの末尾が「開始」の行で止まっていれば、そこが停止位置だと分かる。
    終了時にしかログを出さないと、止まった処理の痕跡は永久に残らない。

    副次的に、各メソッドの所要時間も分かる（遅い処理の発見）。

    **引数・戻り値は記録しない。** 秘密の値（DPAPI のトークン・client_secret・
    パスワード）がログへ載る危険を避けるため。「どのファイルで止まったか」を
    知りたいときは、呼び出し側が処理対象をログへ出す（ライブラリの責務は
    「どのメソッドで止まったか」まで）。

    雛形プロジェクトでは `config.RUN.DEBUG` で `with debug():` の on/off を
    切り替えられる。止まったときに非エンジニアが自分で「デバッグモードで再実行」
    できるよう、`config.ini` からのスイッチを前提にしている。

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
        - ExcelWriter.save / ExcelComHandler.save / CsvWriter の書き込み
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
