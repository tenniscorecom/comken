"""
サンプル: CSV の指定列とファイル名の日付を照合して移動する

事前準備:
    config.ini.example を config.ini にコピーし、フォルダ・日付列名・書式等を書き換える。

実行方法:
    リポジトリのルートで python -m examples.advanced.csv_date_move.run
"""

import datetime
import logging
from pathlib import Path

from comken import Config, dry_run
from comken.core import date_in_name, move_file
from comken.toolbox.csv import CSV

HERE = Path(__file__).parent
CONFIG_PATH = HERE / "config.ini"

logger = logging.getLogger(__name__)


def move_matching_files(
    input_folder: Path,
    output_folder: Path,
    date_column: str,
    date_format: str,
    pattern: str,
) -> tuple[int, int]:
    """内容とファイル名の日付が一致する CSV だけを移動する。"""
    processed_count = 0
    skipped_count = 0
    paths = sorted(
        (path for path in input_folder.glob(pattern) if date_in_name(path.name)),
        key=lambda path: date_in_name(path.name),
        reverse=True,
    )

    for path in paths:
        try:
            # ヘッダー名で読むため、列の位置が変わっても同じ値を取得できる。
            with CSV(path) as csv_file:
                date_value = csv_file.read()[0][date_column]
            try:
                # NOTE: CSV に書かれた業務日付の解析であり、タイムゾーンは不要。
                content_date = datetime.datetime.strptime(  # noqa: DTZ007
                    date_value, date_format
                ).date()
            except ValueError as error:
                raise ValueError(
                    f"{path.name} の「{date_column}」列の値「{date_value}」を"
                    "日付として読めません。"
                    f"設定 DATE_FORMAT（{date_format}）とCSVの書式を確認してください。"
                ) from error

            name_date = date_in_name(path.name)
            if content_date != name_date:
                logger.warning(
                    "スキップ: %s（「%s」列は %s、ファイル名の日付は %s）",
                    path.name,
                    date_column,
                    content_date,
                    name_date,
                )
                skipped_count += 1
                continue

            move_file(path, output_folder / path.name)
            logger.info("処理: %s を %s へ移動しました", path.name, output_folder)
            processed_count += 1
        except Exception as error:
            logger.warning("スキップ: %s（%s）", path.name, error)
            skipped_count += 1

    logger.info("処理 %d 件 / スキップ %d 件", processed_count, skipped_count)
    return processed_count, skipped_count


def main() -> None:
    config = Config(CONFIG_PATH)
    with dry_run():
        move_matching_files(
            config.FILES.INPUT_FOLDER,
            config.FILES.OUTPUT_FOLDER,
            config.CSV.DATE_COLUMN,
            config.CSV.DATE_FORMAT,
            config.CSV.PATTERN,
        )


if __name__ == "__main__":
    main()
