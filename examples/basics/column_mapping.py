"""サンプル: 列マッピングをコードと config.ini の2通りから渡す。"""

import logging
from pathlib import Path

from comken import Config
from comken.core.logger import local
from comken.core.table import Table, Transfer
from comken.toolbox.csv import CSV
from comken.toolbox.excel import Excel

HERE = Path(__file__).parent
OUTPUT_FOLDER = HERE / "output"
CONFIG_PATH = OUTPUT_FOLDER / "config.ini"
SOURCE_CSV = OUTPUT_FOLDER / "受注.csv"
OUTPUT_PATH = OUTPUT_FOLDER / "請求一覧.xlsx"

logger = logging.getLogger(__name__)


def main() -> None:
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        "[受注_MAPPING]\n取引先 = 顧客名\n金額 = 請求額\n",
        encoding="utf-8",
    )
    with CSV(SOURCE_CSV) as source_csv:
        source_csv.write(
            Table(
                ["注文番号", "取引先", "金額"],
                [{"注文番号": "A001", "取引先": "株式会社アルファ", "金額": 12000}],
            )
        )
    # 部署や拠点で列名が変わり、現場で変更する必要がある場合だけ設定へ出す。
    # 設定変更はテストに守られない業務ルール変更でもあるため、運用時に確認が必要になる。
    # ``config.SECTION_MAPPING`` は ``MappingDict``（dict 互換）。未知の列は ``None`` を返す。
    config_mapping = Config(CONFIG_PATH).受注_MAPPING

    mapping = dict(config_mapping)
    source = CSV(SOURCE_CSV, read_only=True, types={"金額": int}).read()
    destination_table = Table(
        ["注文番号", "顧客名", "請求額"],
        [{"注文番号": row["注文番号"], "顧客名": "", "請求額": ""} for row in source.read()],
    )
    transfer = Transfer(
        source,
        destination_table,
        mapping=mapping,
        read_key="注文番号",
        write_key="注文番号",
    )
    for read_row, write_row in transfer.matched_rows():
        # mapping の対応関係どおりに転記先に値を流し込む
        for read_column, write_column in mapping.items():
            write_row[write_column] = read_row[read_column]
    working = transfer._working_table
    with Excel(OUTPUT_PATH) as destination:
        destination.create_data_sheet("請求一覧").create_table("請求一覧", working)

    logger.info("設定の列対応: %s（左: 転記元 → 右: 転記先）", config_mapping)
    logger.info("Excel 転記: %s（%d 件）", OUTPUT_PATH, working.count())


if __name__ == "__main__":
    logger = local()
    main()