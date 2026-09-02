"""サンプル: 単体実行向けのログ設定。"""

import logging
from pathlib import Path

from comken.core import today
from comken.core.logger import setup_local_logging

HERE = Path(__file__).parent
LOG_FOLDER = HERE / "output" / "logs"

logger = logging.getLogger(__name__)


def main() -> None:
    # ログ設定はプログラムの入口で一度だけ行い、mainの再実行では既存設定を使う。
    root = logging.getLogger()
    logger = logging.getLogger(__name__)
    if not root.handlers:
        setup_local_logging(path=LOG_FOLDER)
    logger.info("設定済みのログへ出力します")
    logger.info("ログは UTF-8 で出力: %s", LOG_FOLDER / f"{today().isoformat()}.log")


if __name__ == "__main__":
    # 出力先を変えたいときは実行前にフォルダを作って setup_local_logging() を呼ぶ。
    LOG_FOLDER.mkdir(parents=True, exist_ok=True)
    setup_local_logging()
    main()
