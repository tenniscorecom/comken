"""
サンプル: Excel のデータテーブルを読み取る

辞書・タプル・ジェネレーターで表を読む方法を、生成した Excel で示す。

実行方法:
    リポジトリのルートで python -m examples.excel_read
"""

import logging
from pathlib import Path

from comken.core.logger import setup_local_logging
from comken.core.table import Table
from comken.toolbox.excel import Excel

HERE = Path(__file__).parent
EXCEL_PATH = HERE / "output" / "在庫一覧.xlsx"
SHEET_NAME = "在庫"

logger = logging.getLogger(__name__)


def main() -> None:
    with Excel(EXCEL_PATH) as excel:
        excel.create_data_sheet(SHEET_NAME).create_table(
            SHEET_NAME,
            Table(
                ["商品コード", "商品名", "在庫数"],
                [
                    {"商品コード": "P001", "商品名": "コピー用紙", "在庫数": 25},
                    {"商品コード": "P002", "商品名": "ボールペン", "在庫数": 40},
                ],
            ),
        )

    with Excel(EXCEL_PATH, read_only=True) as excel:
        records = excel.data_sheet(SHEET_NAME).table().read()

    logger.info("辞書で読んだ先頭行: %s", records[0])
    logger.info("読み取り: %d 件", len(records))


if __name__ == "__main__":
    logger = setup_local_logging()
    main()
