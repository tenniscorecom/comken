"""
サンプル: CSV と Table の主要な読み取り方法

ヘッダー名で安全に値を読む方法、セル位置で読む方法、検索・抽出・索引・グループ化を示す。

実行方法:
    リポジトリのルートで python -m examples.basics.csv_read
"""

import logging
from pathlib import Path

from comken.core.logger import setup_local_logging
from comken.toolbox.csv import CSV

HERE = Path(__file__).parent
CSV_PATH = HERE / "output" / "受注明細.csv"

logger = logging.getLogger(__name__)


def main() -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    CSV_PATH.write_text(
        "注文番号,得意先,担当者,金額\n"
        "A001,株式会社アルファ,山田,12000\n"
        "A002,株式会社ベータ,佐藤,8500\n"
        "A003,株式会社ガンマ,山田,4300\n",
        encoding="utf-8",
    )
    with CSV(CSV_PATH) as csv_file:
        table = csv_file.read()
    rows = table.read()
    logger.info("全行: %d 件（先頭: %s）", len(rows), rows[0])

    # ヘッダーがある CSV は列順が変わっても壊れない first() を選ぶ。
    logger.info("最初の得意先: %s", rows[0]["得意先"])
    found = table.index("注文番号")["A002"]
    logger.info("A002 の担当者: %s", found["担当者"])
    logger.info("山田の受注: %d 件", table.filter(lambda row: row["担当者"] == "山田").count())
    logger.info("金額列: %s", table.column("金額"))

    # 重複しない注文番号は index()、複数行あり得る担当者は group_by() を使う。
    orders = table.index("注文番号")
    orders_by_staff = table.group_by("担当者")
    logger.info("索引 A003: %s / 山田グループ: %d 件", orders["A003"], len(orders_by_staff["山田"]))


if __name__ == "__main__":
    logger = setup_local_logging()
    main()
