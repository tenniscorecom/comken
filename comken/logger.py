"""単体実行するプロジェクト向けのログ設定。"""

import logging
from pathlib import Path

from .runtime import is_debug
from .utils.clock import today

__all__ = ["setup_logging"]

LOG_DIR = Path("logs")
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(to_file: bool = True) -> None:
    """単体実行向けに、コンソールと日付別ファイルへのログ出力を設定する。

    社内 RPA 基盤がログを設定する実行では呼び出す必要はない。すでに root logger に
    ハンドラがある場合は、既存の出力先・書式・レベルを変更せず、そのまま返る。

    Args:
        to_file: True なら ``logs/YYYY-MM-DD.log`` にも UTF-8 で出力する。
    """
    root_logger = logging.getLogger()
    # RPA 基盤や利用側が設定済みなら、その出力先・書式・レベルを壊さないため何もしない。
    if root_logger.handlers:
        return

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if to_file:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = LOG_DIR / f"{today().isoformat()}.log"
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))

    for handler in handlers:
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    # 詳細な処理時間を調べるデバッグモードでは、DEBUG ログも見えるようにする。
    root_logger.setLevel(logging.DEBUG if is_debug() else logging.INFO)
