"""サンプル: comken の例外を粒度に応じて捕まえる。"""

import logging
from pathlib import Path

from comken.core.logger import setup_local_logging
from comken.exceptions import ComkenError, TableColumnNotFoundError
from comken.toolbox.csv import CSV

HERE = Path(__file__).parent
CSV_PATH = HERE / "output" / "例外確認.csv"

logger = logging.getLogger(__name__)


def main() -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    CSV_PATH.write_text("注文番号,金額\nA001,12000\n", encoding="utf-8")

    try:
        with CSV(CSV_PATH) as csv_file:
            csv_file.read().column("存在しない列")
    except TableColumnNotFoundError as error:
        # この失敗だけ処理を分けたい場合は、個別例外を捕まえる。
        logger.error("個別に捕捉: %s", error)

    empty_csv_path = CSV_PATH.with_name("データなし.csv")
    empty_csv_path.write_text("注文番号,金額\n", encoding="utf-8")
    try:
        with CSV(empty_csv_path) as csv_file:
            csv_file.read().column("存在しない列")
    except ComkenError as error:
        # 機能を問わず処理末尾でまとめるなら ComkenError を使う。
        logger.error("comken 全体で捕捉: %s", error)

    # メッセージ自体に対処法があり、例外名から ERRORS.md でも詳しく引ける。
    logger.info("運用時は表示された例外名を ERRORS.md で検索してください")


if __name__ == "__main__":
    logger = setup_local_logging()
    main()
