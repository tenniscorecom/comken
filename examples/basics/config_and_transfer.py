"""
サンプル: config.ini の列対応表を使って Excel へ転記する

Config.mapping() と Sheet.transfer_by_mapping() を一続きで示す。

実行方法:
    リポジトリのルートで python -m examples.basics.config_and_transfer
"""

import logging
from pathlib import Path

from comken import Config
from comken.csv import CsvReader, CsvWriter
from comken.excel import ExcelWriter
from comken.logger import setup_logging

HERE = Path(__file__).parent
OUTPUT_FOLDER = HERE / "output"
CONFIG_PATH = OUTPUT_FOLDER / "config.ini"
SOURCE_CSV = OUTPUT_FOLDER / "顧客マスタ.csv"
OUTPUT_PATH = OUTPUT_FOLDER / "請求先一覧.xlsx"
SHEET_NAME = "請求先"
MAPPING_SECTION = "顧客_MAPPING"

logger = logging.getLogger(__name__)


def main() -> None:
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    # MAPPING セクションだけは日本語の列名を保つ。左が転記元、右が転記先。
    CONFIG_PATH.write_text(
        "[顧客_MAPPING]\n会社名 = 請求先名\n電話番号 = 連絡先\n",
        encoding="utf-8",
    )
    CsvWriter(SOURCE_CSV, ["顧客コード", "会社名", "電話番号"]).write_rows(
        [
            {"顧客コード": "C001", "会社名": "株式会社アルファ", "電話番号": "03-1111-2222"},
            {"顧客コード": "C002", "会社名": "株式会社ベータ", "電話番号": "06-3333-4444"},
        ]
    )
    lookup = CsvReader(SOURCE_CSV).index("顧客コード")
    mapping = Config(CONFIG_PATH).mapping(MAPPING_SECTION)

    with ExcelWriter.create(OUTPUT_PATH, sheet_name=SHEET_NAME) as writer:
        sheet = writer.sheet(SHEET_NAME)
        sheet.write_table(
            [
                {"顧客コード": "C001", "請求先名": "", "連絡先": ""},
                {"顧客コード": "C002", "請求先名": "", "連絡先": ""},
                {"顧客コード": "C999", "請求先名": "", "連絡先": ""},
            ]
        )
        matched = sheet.transfer_by_mapping("顧客コード", lookup, mapping)
        writer.save()

    logger.info("列対応: %s（左: 転記元 → 右: 転記先）", mapping)
    logger.info("Excel 転記: %s（%d 件一致）", OUTPUT_PATH, matched)


if __name__ == "__main__":
    setup_logging(to_file=False)
    main()
