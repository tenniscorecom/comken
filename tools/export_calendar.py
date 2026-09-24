"""tools/export_calendar.py — comken.core.calendar.export_csv の薄いラッパー。

国民の祝日（内閣府 CSV + 計算値）と会社休日を 1948-2099 年ぶんの CSV として
``comken/core/calendar/data/holidays.csv`` に書き出す。年 1 回の内閣府 CSV
差し替え（→ ``syukujitsu.csv`` を更新）と、会社休日ルール変更
（→ ``comken/core/calendar/company.py`` の ``COMPANY_HOLIDAYS`` /
``COMPANY_HOLIDAYS_EXTRA`` を編集）のあとにこのツールを走らせて、
``data/holidays.csv`` を更新しコミットする。

``holidays.csv`` は git 管理下で追跡される。Excel・VBA 側はここから
祝日＋会社休日を読み取って営業日判定に使う。

使い方::

    python tools\\export_calendar.py

``--path`` で任意の書き出し先を指定できる::

    python tools\\export_calendar.py --path tmp/holidays.csv
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

# スクリプト実行時に tools/ が sys.path 先頭に入るため、リポジトリルートを
# 明示的に追加して comken を import する
ROOT = Path(__file__).resolve().parent.parent
import sys  # noqa: E402

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from comken.core.calendar import EXPORTED_CSV_PATH, export_csv  # noqa: E402

logger = logging.getLogger(__name__)


def main() -> None:
    """``export_csv`` を ``EXPORTED_CSV_PATH`` に実行する。"""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--path",
        type=Path,
        default=EXPORTED_CSV_PATH,
        help="書き出し先（省略時は comken/core/calendar/data/holidays.csv）",
    )
    args = parser.parse_args()

    written = export_csv(args.path)
    logger.info("書き出し完了: %s", written)


if __name__ == "__main__":
    main()
