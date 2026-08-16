"""
サンプル: ExcelReader の主要な読み取り方法

辞書・タプル・ジェネレーターで表を読む方法を、生成した Excel で示す。

実行方法:
    リポジトリのルートで python -m examples.basics.excel_read
"""

import logging
from pathlib import Path

from comken import setup_logging
from comken.toolbox.excel import ExcelReader, ExcelWriter

HERE = Path(__file__).parent
EXCEL_PATH = HERE / "output" / "在庫一覧.xlsx"
SHEET_NAME = "在庫"

logger = logging.getLogger(__name__)


def main() -> None:
    with ExcelWriter.create(EXCEL_PATH, sheet_name=SHEET_NAME) as writer:
        writer.sheet(SHEET_NAME).write_table(
            [
                {"商品コード": "P001", "商品名": "コピー用紙", "在庫数": 25},
                {"商品コード": "P002", "商品名": "ボールペン", "在庫数": 40},
            ]
        )
        writer.save()

    # 読み取り専用のブックは with で閉じ、次の処理がファイルを使える状態に戻す。
    with ExcelReader(EXCEL_PATH) as reader:
        records = reader.read_rows_as_dicts(SHEET_NAME)
        rows = reader.read_rows(SHEET_NAME)
        streamed_rows = list(reader.iter_rows(SHEET_NAME))

    logger.info("辞書で読んだ先頭行: %s", records[0])
    logger.info("タプル: %d 件 / 逐次読み取り: %d 件", len(rows), len(streamed_rows))


if __name__ == "__main__":
    setup_logging(to_file=False)
    main()
