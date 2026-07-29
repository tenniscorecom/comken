"""
src/run.py — 処理の本体

main.py から呼ばれる。ここに「実際にやりたいこと」を書く。
下は「CSV を読んで Excel レポートを作る」最小例。不要なら丸ごと書き換えてよい。
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SHEET = "Sheet1"


def run(output_folder: Path) -> None:
    """処理の入口。main.py から config の値を受け取って実行する。

    Args:
        output_folder: 出力先フォルダ（config.ini の [REPORT] OUTPUT_FOLDER）。
    """
    # ── ここに処理を書く ──────────────────────────────────────────────
    # 例:
    #   from comken.csv import CsvReader
    #   from comken.excel import ExcelFile
    #   from comken.naming import DateNameBuilder
    #
    #   from comken import config   # config.FILES. まで打つと補完が出る
    #
    #   rows = CsvReader(config.FILES.INPUT_CSV).rows()
    #   out = output_folder / DateNameBuilder("レポート").prefix()
    #   with ExcelFile.create(out) as f:
    #       s = f.sheet(SHEET)
    #       s.write_table(rows)
    #       s.auto_width()
    #       f.save()
    #   logger.info("出力しました: %s", out)
    # ──────────────────────────────────────────────────────────────────
    logger.info("run() を実装してください（出力先: %s）", output_folder)
