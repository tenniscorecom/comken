"""
サンプル: ExcelWriter と Sheet で見やすい帳票を作る

表の書き込み、書式、列幅、ヘッダー固定、構造化テーブル化までを示す。

実行方法:
    リポジトリのルートで python -m examples.basics.excel_write
"""

import logging
from pathlib import Path

from comken.constants import Color
from comken.logger import setup_logging
from comken.toolbox.excel import ExcelWriter

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
    with ExcelWriter.create(OUTPUT_PATH, sheet_name=SHEET_NAME) as writer:
        sheet = writer.sheet(SHEET_NAME)
        sheet.write_table(sales_rows)
        for column in range(1, len(sales_rows[0]) + 1):
            sheet.set_fill(HEADER_ROW, column, Color.LIGHT_BLUE)
            sheet.set_bold(HEADER_ROW, column)
        for row in range(HEADER_ROW + 1, sheet.last_row + 1):
            sheet.set_number_format(row, "D", "#,##0")
        sheet.auto_width()
        sheet.freeze_header()
        # フィルターや縞模様を使える帳票にするため、値を書いた後に構造化する。
        sheet.add_table(TABLE_NAME, TABLE_REF)
        writer.save()

    logger.info("Excel 帳票出力: %s（%d 件）", OUTPUT_PATH, len(sales_rows))


if __name__ == "__main__":
    setup_logging(to_file=False)
    main()
