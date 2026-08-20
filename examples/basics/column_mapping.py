"""サンプル: 列マッピングをコードと config.ini の2通りから渡す。"""

import logging
from pathlib import Path

from comken import Config, setup_logging
from comken.toolbox import Transfer
from comken.toolbox.csv import CsvReader, CsvWriter
from comken.toolbox.excel import ExcelWriter

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
    CsvWriter(SOURCE_CSV, ["注文番号", "取引先", "金額"]).write_rows(
        [{"注文番号": "A001", "取引先": "株式会社アルファ", "金額": 12000}]
    )
    # 部署や拠点で列名が変わり、現場で変更する必要がある場合だけ設定へ出す。
    # 設定変更はテストに守られない業務ルール変更でもあるため、運用時に確認が必要になる。
    # ``config.SECTION_MAPPING`` は ``MappingDict``（dict 互換）。未知の列は ``None`` を返す。
    config_mapping = Config(CONFIG_PATH).受注_MAPPING

    mapping = dict(config_mapping)
    source = CsvReader(SOURCE_CSV)
    with ExcelWriter.create(OUTPUT_PATH) as destination:
        transferred = Transfer(source, destination.sheet("Sheet1"), mapping).run()
        destination.save()

    logger.info("設定の列対応: %s（左: 転記元 → 右: 転記先）", config_mapping)
    logger.info("Excel 転記: %s（%d 件）", OUTPUT_PATH, transferred)


if __name__ == "__main__":
    setup_logging(to_file=False)
    main()
