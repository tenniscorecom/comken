"""サンプル: comken の例外を粒度に応じて捕まえる。"""

from __future__ import annotations

import logging
from pathlib import Path

from comken.csv import CsvReader
from comken.exceptions import ComkenError, CsvError, CsvRowNotFoundError
from comken.logger import setup_logging

HERE = Path(__file__).parent
CSV_PATH = HERE / "output" / "例外確認.csv"

logger = logging.getLogger(__name__)


def main() -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    CSV_PATH.write_text("注文番号,金額\nA001,12000\n", encoding="utf-8")

    try:
        CsvReader(CSV_PATH).find("注文番号", "Z999")
    except CsvRowNotFoundError as error:
        # この失敗だけ処理を分けたい場合は、個別例外を捕まえる。
        logger.error("個別に捕捉: %s", error)

    empty_csv_path = CSV_PATH.with_name("データなし.csv")
    empty_csv_path.write_text("注文番号,金額\n", encoding="utf-8")
    try:
        CsvReader(empty_csv_path).first("注文番号")
    except CsvError as error:
        # CSV の失敗を同じ扱いにするならカテゴリ基底を捕まえる。
        logger.error("CSV カテゴリで捕捉: %s", error)
    except ComkenError as error:
        # 機能を問わず処理末尾でまとめるなら ComkenError を使う。
        logger.error("comken 全体で捕捉: %s", error)

    # メッセージ自体に対処法があり、例外名から ERRORS.md でも詳しく引ける。
    logger.info("運用時は表示された例外名を ERRORS.md で検索してください")


if __name__ == "__main__":
    setup_logging(to_file=False)
    main()
