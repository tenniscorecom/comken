"""サンプル: 日付入りファイルの検索・命名・移動・コピー・zip。"""

import logging
from pathlib import Path

from comken.core import (
    DateNameBuilder,
    copy_file,
    date_in_name,
    move_file,
    unzip,
    zip_files,
)
from comken.core.logger import setup_local_logging

HERE = Path(__file__).parent
OUTPUT_FOLDER = HERE / "output" / "files"
ARCHIVE_PATH = OUTPUT_FOLDER / "日次資料.zip"

logger = logging.getLogger(__name__)


def main() -> None:
    input_folder = OUTPUT_FOLDER / "input"
    archive_folder = OUTPUT_FOLDER / "archive"
    extract_folder = OUTPUT_FOLDER / "展開"
    input_folder.mkdir(parents=True, exist_ok=True)
    for name in ("売上_2026-08-11.csv", "売上_20260812.csv", "売上_日付なし.csv"):
        (input_folder / name).write_text("注文番号,金額\nA001,12000\n", encoding="utf-8")

    dated_files = sorted(
        (path for path in input_folder.glob("売上_*.csv") if date_in_name(path.name)),
        key=lambda path: date_in_name(path.name),
        reverse=True,
    )
    logger.info("日付入りファイル（新しい順）: %s", [path.name for path in dated_files])
    logger.info(
        "名前順の最新: %s", max(input_folder.glob("*.csv"), key=lambda path: path.name).name
    )

    builder = DateNameBuilder("売上レポート.csv")
    copied = copy_file(dated_files[0], OUTPUT_FOLDER / builder.suffix())
    moved = move_file(dated_files[1], archive_folder / dated_files[1].name)
    logger.info("コピー: %s / 移動: %s", copied.name, moved.name)

    zip_files([copied, moved], ARCHIVE_PATH)
    unzip(ARCHIVE_PATH, extract_folder)
    logger.info("zip: %s / 展開: %s", ARCHIVE_PATH, extract_folder)


if __name__ == "__main__":
    logger = setup_local_logging()
    main()
