"""サンプル: 生の値ではなく公開定数を使って選択肢を指定する。"""

import logging
from pathlib import Path

from comken.constants import Color, Encoding, FileFormat
from comken.core.logger import local
from comken.toolbox.csv import CsvReader, CsvWriter

HERE = Path(__file__).parent
OUTPUT_FOLDER = HERE / "output" / "constants"
CSV_PATH = OUTPUT_FOLDER / "名簿.csv"

logger = logging.getLogger(__name__)


def main() -> None:
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    # 定数なら IDE の補完が効き、"utf8-sgi" のような打ち間違いを防げる。
    CsvWriter(CSV_PATH, ["社員番号", "氏名"], encoding=Encoding.UTF8_SIG).write_rows(
        [{"社員番号": "001", "氏名": "山田"}]
    )
    rows = CsvReader(CSV_PATH, encoding=Encoding.AUTO).read_rows()
    latest = max(OUTPUT_FOLDER.glob("*.csv"), key=lambda path: path.stat().st_mtime)

    logger.info("Encoding: %s（%d 件）", Encoding.UTF8_SIG, len(rows))
    logger.info("更新日時が最新のCSV: %s", latest.name)
    logger.info("Color: %s（Excel の色指定）", Color.LIGHT_BLUE)
    logger.info("FileFormat: %s（Excel COM の xlsx 保存形式）", FileFormat.XLSX)


if __name__ == "__main__":
    logger = local()
    main()
