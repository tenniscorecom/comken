"""
src/run.py — 処理の本体

main.py から呼ばれる。ここに「実際にやりたいこと」を書く。
下は「CSV を読んで Excel レポートを作る」最小例。不要なら丸ごと書き換えてよい。
"""

import logging

from comken import config

logger = logging.getLogger(__name__)

SHEET = "Sheet1"


def run() -> None:
    """処理の入口。main.py から呼ばれる。"""
    # config.SECTION.KEY で config.ini（プロジェクト直下）の値を読む。
    # config.FILES. まで打つと Pylance で補完が出る（typings スタブは自動生成）。
    output_folder = config.FILES.OUTPUT_FOLDER

    # ── ここに処理を書く ──────────────────────────────────────────────
    # 例:
    #   from comken.toolbox.csv import CsvReader
    #   from comken.toolbox.excel import ExcelWriter
    #   from comken.core import DateNameBuilder
    #
    #   rows = CsvReader(config.FILES.INPUT_CSV).read_rows()
    #   out = output_folder / DateNameBuilder("レポート").prefix()
    #   with ExcelWriter.create(out) as f:
    #       s = f.sheet(SHEET)
    #       s.write_table(rows)
    #       s.auto_width()
    #       f.save()
    #   logger.info("出力しました: %s", out)
    # ──────────────────────────────────────────────────────────────────
    logger.info("run() を実装してください（出力先: %s）", output_folder)
