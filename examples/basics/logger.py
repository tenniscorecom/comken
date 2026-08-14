"""サンプル: 単体実行向けのログ設定。"""

from __future__ import annotations

import logging
from pathlib import Path

import comken.logger as comken_logger
from comken.logger import setup_logging
from comken.utils import today

HERE = Path(__file__).parent
LOG_FOLDER = HERE / "output" / "logs"

logger = logging.getLogger(__name__)


def main() -> None:
    # 社内 RPA 基盤がログを設定済みなら呼ばない。既存ハンドラがあれば何もしない。
    handlers_before = len(logging.getLogger().handlers)
    setup_logging()
    handlers_after = len(logging.getLogger().handlers)
    logger.info("設定済みの場合は維持: ハンドラ数 %d → %d", handlers_before, handlers_after)
    logger.info("ログは UTF-8 で出力: %s", LOG_FOLDER / f"{today().isoformat()}.log")


if __name__ == "__main__":
    comken_logger.LOG_DIR = LOG_FOLDER
    setup_logging()
    main()
