"""comken/runtime.py — ライブラリ全体の実行モード（デバッグ・dry-run）

dry-run モードとデバッグモードの**プロセス設定**を管理する。
それぞれの「有効か」を返す `is_dry_run()` / `is_debug()` の戻り値は、
次の順で決定される。

1. **プロセスの setter** (`set_dry_run()` / `set_debug()`) が呼ばれていれば、
   その値をそのまま返す。None を渡すと解除され、2 へ進む。
2. **環境変数** `COMKEN_DRY_RUN` / `COMKEN_DEBUG` を読む。
   `"1"` / `"true"` / `"yes"` / `"on"`（大小文字区別なし）が真、
   空文字列・未設定は偽。
3. どちらでも無ければ **False**。

`config.ini` を読まない。**設定ファイルを触らずコード上から切り替えたい**
場面（dry-run で再実行したいときなど）を優先する設計。
`with dry_run():` / `with debug():` コンテキストは setter を一時的に
書き換えるだけで、終了時に開始前の状態（setter 値、または環境変数）へ戻す。
"""

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# 各モードの「明示的に設定された値」。None のときは環境変数に従う。
_dry_run_override: bool | None = None
_debug_override: bool | None = None

# 環境変数を真とみなす値（大文字小文字を区別しない）。
_TRUE_FLAGS = frozenset({"1", "true", "yes", "on"})


def _env_flag(name: str) -> bool:
    """環境変数が真偽値として真かどうか。

    "1", "true", "yes", "on" を True 扱い。大文字小文字は区別しない。
    空文字列や未設定は False。
    """
    raw = os.environ.get(name, "")
    return raw.strip().lower() in _TRUE_FLAGS


def is_dry_run() -> bool:
    """dry-run モードが有効か返す。

    優先順位: プロセスの setter > 環境変数 (COMKEN_DRY_RUN) > 既定値 False。

    有効にすると、外部に影響する操作（ファイル書き込み、Salesforce 送信、
    state.ini 書き込み等）を実行せず、何をするはずだったかを INFO ログ
    （[DRY-RUN] プレフィックス付き）に出す。読み取りは通常どおり実行される。
    """
    if _dry_run_override is not None:
        return _dry_run_override
    return _env_flag("COMKEN_DRY_RUN")


def is_debug() -> bool:
    """デバッグモードが有効か返す。

    優先順位: プロセスの setter > 環境変数 (COMKEN_DEBUG) > 既定値 False。

    有効にすると、`@measure` を付けたメソッドの出入りを DEBUG ログに
    記録する。業務バッチが外部待ち（ブラウザ・HTTP・Excel COM・共有サーバー）
    で止まったとき、ログの末尾が「開始」の行で止まっていれば、そこが
    停止位置だと分かる。
    """
    if _debug_override is not None:
        return _debug_override
    return _env_flag("COMKEN_DEBUG")


def set_dry_run(enabled: bool | None) -> None:
    """dry-run モードを強制設定する。

    True / False を渡すと、is_dry_run() が必ずその値を返す（環境変数を上書き）。
    None を渡すと解除し、以降は環境変数に従う。

    config.ini を開かずに dry-run を切り替えたいときや、CLI から
    フラグで指定した値を反映したいときに使う。
    """
    global _dry_run_override
    _dry_run_override = enabled


def set_debug(enabled: bool | None) -> None:
    """デバッグモードを強制設定する。

    True / False を渡すと、is_debug() が必ずその値を返す（環境変数を上書き）。
    None を渡すと解除し、以降は環境変数に従う。
    """
    global _debug_override
    _debug_override = enabled


@contextmanager
def dry_run(enabled: bool = True) -> Iterator[None]:
    """ブロック内だけ dry-run モードを指定した状態にする。

    終了時に元の状態（プロセスの setter 値、または環境変数）に戻す。
    ブロック内で `set_dry_run(None)` を呼んだ場合は None に戻る
    （環境変数に従う）。

    Args:
        enabled: True で有効（デフォルト）。False ならブロック内だけ無効。
                 外側が dry-run 中でも、このブロックでは通常どおり書き込む。
    """
    previous = _dry_run_override
    set_dry_run(enabled)
    try:
        yield
    finally:
        set_dry_run(previous)


@contextmanager
def debug(enabled: bool = True) -> Iterator[None]:
    """ブロック内だけデバッグモードを指定した状態にする。

    終了時に元の状態（プロセスの setter 値、または環境変数）に戻す。

    Args:
        enabled: True で有効（デフォルト）。False ならブロック内だけ無効。
    """
    previous = _debug_override
    set_debug(enabled)
    try:
        yield
    finally:
        set_debug(previous)


def dry_run_log(action: str, *args) -> None:
    """dry-run でスキップした操作をログに出す（ライブラリ内部用）。

    Args:
        action: ログに出す文字列。`args` を ``%`` でフォーマットする。
                `args` を渡さなければそのまま INFO ログへ。
    """
    logger.info("[DRY-RUN] %s", action % args if args else action)
