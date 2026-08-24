"""サンプル: debug と dry_run の実行範囲を限定する。"""

import logging
from pathlib import Path

from comken import debug, dry_run
from comken.core import copy_file
from comken.core.logger import setup_local_logging

HERE = Path(__file__).parent
OUTPUT_FOLDER = HERE / "output"
SOURCE_PATH = OUTPUT_FOLDER / "コピー元.txt"
DRY_RUN_PATH = OUTPUT_FOLDER / "dry-runでは作られない.txt"
ACTUAL_PATH = OUTPUT_FOLDER / "本番コピー.txt"

logger = logging.getLogger(__name__)


def main() -> None:
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    SOURCE_PATH.write_text("確認用", encoding="utf-8")
    DRY_RUN_PATH.unlink(missing_ok=True)

    logger.info("ブロック外（既定の状態）に入ります")
    with debug():
        logger.info("debug ブロック内です")
    logger.info("debug ブロックを抜けました")

    with dry_run():
        logger.info("dry-run ブロック内です")
        copy_file(SOURCE_PATH, DRY_RUN_PATH)
    logger.info("dry-run の出力ファイルあり: %s", DRY_RUN_PATH.exists())

    copy_file(SOURCE_PATH, ACTUAL_PATH)
    logger.info("通常実行の出力ファイルあり: %s", ACTUAL_PATH.exists())


if __name__ == "__main__":
    logger = setup_local_logging()
    main()
