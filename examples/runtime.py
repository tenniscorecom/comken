"""サンプル: debug と dry_run の実行範囲を限定する。

`main.py` の ``comken_logger.setup_local_logging()`` 直下に置く定型は
``comken.runtime.run_main(main, *, debug_mode=False, dry_run_mode=False)``
にまとめられる（``docs/機能/core.md「main の定型（run_main）」節``）。

::

    def main() -> int:
        return run()

    if __name__ == "__main__":
        comken_logger.setup_local_logging()
        raise SystemExit(run_main(main, debug_mode=True, dry_run_mode=True))

``run()`` の戻り値が ``int`` ならそのまま、``None`` なら ``0``。
``ComkenError`` は ``logger.error`` して ``1``、想定外例外は
``logger.exception`` した上でそのまま再送出する。
"""

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
    setup_local_logging()
    main()
