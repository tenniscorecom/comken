"""サンプル: debug と dry_run の実行範囲を限定する。"""

import logging
from pathlib import Path

from comken import debug, dry_run, is_debug, is_dry_run
from comken.core.logger import setup_logging
from comken.core.utils.files import copy_file

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

    with debug():
        logger.info("debug ブロック内: %s", is_debug())
    logger.info("debug ブロック外: %s", is_debug())

    with dry_run():
        logger.info("dry-run ブロック内: %s", is_dry_run())
        copy_file(SOURCE_PATH, DRY_RUN_PATH)
    logger.info("dry-run の出力ファイルあり: %s", DRY_RUN_PATH.exists())

    copy_file(SOURCE_PATH, ACTUAL_PATH)
    logger.info("通常実行の出力ファイルあり: %s", ACTUAL_PATH.exists())


if __name__ == "__main__":
    setup_logging(to_file=False)
    main()
