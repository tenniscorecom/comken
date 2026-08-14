"""サンプル: 列マッピングをコードと config.ini の2通りから渡す。"""

import logging
from pathlib import Path

from comken import Config
from comken.csv import CsvReader, CsvWriter
from comken.excel import ExcelWriter
from comken.logger import setup_logging

HERE = Path(__file__).parent
OUTPUT_FOLDER = HERE / "output"
CONFIG_PATH = OUTPUT_FOLDER / "config.ini"
SOURCE_CSV = OUTPUT_FOLDER / "受注.csv"
OUTPUT_PATH = OUTPUT_FOLDER / "請求一覧.xlsx"
CODE_SHEET = "コードで指定"
CONFIG_SHEET = "設定で指定"
MAPPING_SECTION = "受注_MAPPING"

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
    lookup = CsvReader(SOURCE_CSV).index("注文番号")

    # どの環境でも同じ業務ルールなら、補完・型・テストが効くコードを既定にする。
    code_mapping = {"取引先": "顧客名", "金額": "請求額"}
    # 部署や拠点、年度で列名が変わり、現場で変更する必要がある場合だけ設定へ出す。
    # 設定変更はテストに守られない業務ルール変更でもあるため、運用時に確認が必要になる。
    config_mapping = Config(CONFIG_PATH).mapping(MAPPING_SECTION)

    with ExcelWriter.create(OUTPUT_PATH, sheet_name=CODE_SHEET) as writer:
        writer.add_sheet(CONFIG_SHEET)
        for sheet_name, mapping in (
            (CODE_SHEET, code_mapping),
            (CONFIG_SHEET, config_mapping),
        ):
            sheet = writer.sheet(sheet_name)
            sheet.write_table([{"注文番号": "A001", "顧客名": "", "請求額": ""}])
            sheet.transfer_by_mapping("注文番号", lookup, mapping)
        writer.save()

    # 両方式とも左が転記元、右が転記先。逆にしてもエラーにならず逆方向へ転記される。
    logger.info("コードの列対応: %s（左: 転記元 → 右: 転記先）", code_mapping)
    logger.info("設定の列対応: %s（左: 転記元 → 右: 転記先）", config_mapping)
    logger.info("Excel 転記: %s", OUTPUT_PATH)


if __name__ == "__main__":
    setup_logging(to_file=False)
    main()
