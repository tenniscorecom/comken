"""
サンプル: CsvWriter で CSV を新規作成し、行を追記する

実行方法:
    リポジトリのルートで python -m examples.basics.csv_write
"""

import logging
from pathlib import Path

from comken.core.logger import local
from comken.toolbox.csv import CsvReader, CsvWriter

HERE = Path(__file__).parent
OUTPUT_PATH = HERE / "output" / "作業記録.csv"
FIELDNAMES = ["日時", "担当者", "処理件数"]

logger = logging.getLogger(__name__)


def main() -> None:
    writer = CsvWriter(OUTPUT_PATH, FIELDNAMES)
    writer.write_rows(
        [
            {"日時": "2026-08-13 09:00", "担当者": "山田", "処理件数": 12},
            {"日時": "2026-08-13 10:00", "担当者": "佐藤", "処理件数": 8},
        ]
    )
    writer.append_row({"日時": "2026-08-13 11:00", "担当者": "山田", "処理件数": 5})
    writer.append_rows([{"日時": "2026-08-13 12:00", "担当者": "佐藤", "処理件数": 7}])

    rows = CsvReader(OUTPUT_PATH).read_rows()
    logger.info("CSV 出力: %s（%d 件）", OUTPUT_PATH, len(rows))


if __name__ == "__main__":
    logger = local()
    main()
