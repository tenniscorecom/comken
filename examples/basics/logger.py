"""サンプル: 単体実行向けのログ設定。"""

import logging
from pathlib import Path

from comken.core import today
from comken.core.logger import local

HERE = Path(__file__).parent
LOG_FOLDER = HERE / "output" / "logs"

logger = logging.getLogger(__name__)


def main() -> None:
    # 社内 RPA 基盤がログを設定済みなら呼ばない。既存ハンドラがあれば何もしない。
    handlers_before = len(logging.getLogger().handlers)
    logger = local()
    handlers_after = len(logging.getLogger().handlers)
    logger.info("設定済みの場合は維持: ハンドラ数 %d → %d", handlers_before, handlers_after)
    logger.info("ログは UTF-8 で出力: %s", LOG_FOLDER / f"{today().isoformat()}.log")


if __name__ == "__main__":
    # 出力先を変えたいときは実行前にフォルダを作って local() を呼ぶ。
    LOG_FOLDER.mkdir(parents=True, exist_ok=True)
    logger = local()
    main()
