"""
サンプル: Excel と Sheet で見やすい帳票を作る

表の書き込み、書式、列幅、ヘッダー固定、構造化テーブル化までを示す。

実行方法:
    リポジトリのルートで python -m examples.basics.excel_write
"""

import logging
from pathlib import Path

from comken.core.logger import setup_local_logging
from comken.toolbox.excel import Excel

HERE = Path(__file__).parent
OUTPUT_PATH = HERE / "output" / "売上帳票.xlsx"
SHEET_NAME = "売上"
HEADER_ROW = 1
TABLE_NAME = "SalesTable"
TABLE_REF = "A1:D4"

logger = logging.getLogger(__name__)


def main() -> None:
    sales_rows = [
        {"日付": "2026/08/01", "担当者": "山田", "商品": "商品A", "金額": 12000},
        {"日付": "2026/08/02", "担当者": "佐藤", "商品": "商品B", "金額": 8500},
        {"日付": "2026/08/03", "担当者": "山田", "商品": "商品C", "金額": 4300},
    ]
    with Excel(OUTPUT_PATH) as excel:
        sheet = excel.sheet(SHEET_NAME)
        values = [list(sales_rows[0]), *[list(row.values()) for row in sales_rows]]
        sheet.write_range(TABLE_REF, values)
        for column in "ABCD":
            sheet.set_background(f"{column}{HEADER_ROW}", "D9EAF7")
            sheet.format(f"{column}{HEADER_ROW}", bold=True)
        for row in range(HEADER_ROW + 1, len(sales_rows) + 2):
            sheet.format(f"D{row}", number_format="#,##0")
        sheet.freeze_panes("A2")

    logger.info("Excel 帳票出力: %s（%d 件）", OUTPUT_PATH, len(sales_rows))


if __name__ == "__main__":
    logger = setup_local_logging()
    main()
