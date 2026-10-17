"""サンプル: 列マッピングをコードの定数で渡す。"""

import logging
from pathlib import Path

from comken.core.logger import setup_local_logging
from comken.core.table import Table, Transfer
from comken.toolbox.csv import CSV
from comken.toolbox.excel import Excel

HERE = Path(__file__).parent
OUTPUT_FOLDER = HERE / "output"
SOURCE_CSV = OUTPUT_FOLDER / "受注.csv"
OUTPUT_PATH = OUTPUT_FOLDER / "請求一覧.xlsx"

# 転記する列の対応（転記元の見出し → 転記先の見出し）。
TRANSFER_MAPPING = {"取引先": "顧客名", "金額": "請求額"}

logger = logging.getLogger(__name__)


def main() -> None:
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    with CSV(SOURCE_CSV) as source_csv:
        source_csv.replace(
            Table(
                ["注文番号", "取引先", "金額"],
                [{"注文番号": "A001", "取引先": "株式会社アルファ", "金額": 12000}],
            )
        )
    with CSV(SOURCE_CSV, read_only=True, types={"金額": int}) as source_csv:
        source = source_csv.read()
    destination_table = Table(
        ["注文番号", "顧客名", "請求額"],
        [{"注文番号": row["注文番号"], "顧客名": "", "請求額": ""} for row in source.to_rows()],
    )
    transfer = Transfer(
        source,
        destination_table,
        mapping=TRANSFER_MAPPING,
        read_key="注文番号",
        write_key="注文番号",
    )
    for read_row, write_row in transfer.matched_rows():
        # apply_mapping がコンストラクタで渡した mapping を write_row へコピーする
        transfer.apply_mapping(read_row, write_row)
    working = transfer.result()
    with Excel(OUTPUT_PATH) as destination:
        destination.create_data_sheet("請求一覧").create_table("請求一覧", working)

    logger.info("列の対応: %s（左: 転記元 → 右: 転記先）", TRANSFER_MAPPING)
    logger.info("Excel 転記: %s（%d 件）", OUTPUT_PATH, len(working))


if __name__ == "__main__":
    setup_local_logging()
    main()
