"""
雛形: 日次バッチ（当日ファイルの取得 → Excel レポート）

新しい自動化ツールを作るときは、このフォルダをコピーして始めると速い。
「入力ファイルを探す → 加工する → 出力する」という
実務でいちばん多い形に、ログとエラー処理の書き方をひととおり含めてある。

事前準備:
    このフォルダの config.ini.example をコピーして config.ini を作り、
    フォルダパス等を環境に合わせて書き換える。

実行方法:
    リポジトリのルートで python -m examples.daily_batch_template.run
    （実プロジェクトに移すときは main.py にリネームし、templates/実行.bat を組み合わせる）
"""

import logging

from comken.csv import CsvReader
from comken.excel import ExcelWriter
from comken.exceptions import OriginalLibsError
from comken.utils.files import DateNameBuilder, FileFinder

from .config import config

SHEET = "Sheet1"
BATCH_NAME = "日次売上レポート"
INPUT_PATTERN = "*.csv"

logger = logging.getLogger(__name__)


def main() -> None:
    # 入力フォルダから「今日の日付が名前に入ったファイル」を探す。
    # required=False にすると見つからないとき None が返る（エラーにせずスキップ運用できる）
    source = FileFinder(config.FILES.INPUT_FOLDER).today(pattern=INPUT_PATTERN, required=False)
    if source is None:
        logger.info("本日分の入力ファイルがないため何もしません")
        return

    rows = CsvReader(source).rows()
    logger.info("読み込み: %s（%d 件）", source.name, len(rows))

    # ↓↓↓ ここに実際の加工処理を書く（絞り込み・突合・集計など） ↓↓↓

    # ↑↑↑ ここまで ↑↑↑

    output_path = config.REPORT.OUTPUT_FOLDER / DateNameBuilder(BATCH_NAME).prefix()
    with ExcelWriter.create(output_path) as f:
        s = f.sheet(SHEET)
        s.write_table(rows)
        s.auto_width()
        s.freeze_header()
        f.save()
    logger.info("出力: %s", output_path)
    logger.info("%s 完了（%d 件）", BATCH_NAME, len(rows))


if __name__ == "__main__":
    # ログの設定は社内の共通ライブラリ側で行う。ここでは logging をそのまま使う
    # 動きを確認したいだけのとき: from comken import dry_run; with dry_run(): main()
    # （ファイル出力をスキップして、流れだけ [DRY-RUN] ログで確認できる）
    try:
        main()
    except OriginalLibsError as e:
        # comken のエラーはメッセージに対処法が入っている → ログを調査の起点にする
        logger.error("処理を中断しました: %s", e)
        raise
    except Exception:
        logger.error("予期しないエラーが発生しました", exc_info=True)
        raise
