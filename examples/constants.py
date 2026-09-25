"""サンプル: 公開定数の使い方（color は Excel 専用、encoding は文字列で渡す）。"""

import logging
from pathlib import Path

from comken.core.logger import setup_local_logging
from comken.toolbox.csv import CSV
from comken.toolbox.excel import Color

HERE = Path(__file__).parent
OUTPUT_FOLDER = HERE / "output" / "constants"
CSV_PATH = OUTPUT_FOLDER / "名簿.csv"

logger = logging.getLogger(__name__)


def main() -> None:
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    # encoding は文字列で渡す（"utf8-sig" の打ち間違いは normalize_encoding が吸収する）
    with CSV(CSV_PATH, encoding="utf-8-sig") as csv_file:
        csv_file.replace([{"社員番号": "001", "氏名": "山田"}])
    with CSV(CSV_PATH) as csv_file:
        rows = csv_file.read()
    latest = max(OUTPUT_FOLDER.glob("*.csv"), key=lambda path: path.stat().st_mtime)

    logger.info("encoding: utf-8-sig（%d 件）", len(rows))
    logger.info("更新日時が最新のCSV: %s", latest.name)
    logger.info("Color: %s（Excel の色指定）", Color.LIGHT_BLUE)


if __name__ == "__main__":
    setup_local_logging()
    main()
