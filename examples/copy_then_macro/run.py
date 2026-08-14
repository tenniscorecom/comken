r"""サンプル: bat でやっていた「コピー → マクロ → 配る」を Python で書く。

いま bat が大量にある形はこれ:

    copy \\server\share\受信\*.xlsx C:\作業\
    start /wait excel.exe /e "C:\作業\集計.xlsm"     ← マクロを手で動かす日もある
    copy C:\作業\完成.xlsx \\server\share\完成\

同じことを Python で書くと、bat では書けなかった3つが手に入る。

1. **失敗した場所で止まる。** bat の copy は失敗しても次の行へ進むので、
   前日の残りファイルを最新だと思って処理してしまう。
2. **どのファイルを選んだかが決まる。** `*.xlsx` は「そのフォルダに何が入っているか」次第。
   日付で選べば、前日分が残っていても取り違えない。
3. **試運転できる。** `dry_run()` の中では、コピーも保存も実際には行わずログだけ出る。

事前準備:
    Microsoft Excel が入った Windows PC で、下のパスとマクロ名を実際の環境に合わせる。
    マクロ入りブック（.xlsm）は BOOK_NAME の場所に置いておく。

実行方法:
    リポジトリのルートで python -m examples.copy_then_macro.run
"""

import logging
from pathlib import Path

from comken.logger import setup_logging
from comken.toolbox.excel import ExcelWriter
from comken.toolbox.utils.files import FileFinder, copy_file

# 受け取り元・作業場所・配り先。共有フォルダは遅く、Excel が掴んだままになることもあるので、
# **作業はローカルでやって、結果だけ配る**（bat が copy を2回書いていたのと同じ理由）
SOURCE_FOLDER = Path(r"\\server\share\受信")
WORK_FOLDER = Path(r"C:\作業")
DELIVERY_FOLDER = Path(r"\\server\share\完成")

BOOK_NAME = "集計.xlsm"  # マクロ入りブック（作業フォルダに置いてある）
MACRO_NAME = "Module1.日次集計"  # 「モジュール名.プロシージャ名」で指定する
OUTPUT_NAME = "完成.xlsx"

logger = logging.getLogger(__name__)


def main() -> None:
    """当日のデータを作業フォルダへ集め、マクロを動かし、結果を配る。"""
    setup_logging()

    # 1. 当日のデータを受け取る。ファイル名に日付が入っている前提で選ぶ。
    #    見つからなければここで例外になる（bat と違い、古いファイルで先へ進まない）
    source = FileFinder(SOURCE_FOLDER).today(pattern="*.xlsx")
    logger.info("受信ファイル: %s", source.name)

    # 2. 作業フォルダへコピーする。同名があれば上書きされる
    copied = copy_file(source, WORK_FOLDER / source.name)
    logger.info("作業フォルダへコピー: %s", copied)

    # 3. マクロを動かす。ブックを変更するマクロなので保存まで行う（既定で保存する）。
    #    .xlsm は keep_vba で開くので、保存しても VBA が消えない
    book_path = WORK_FOLDER / BOOK_NAME
    with ExcelWriter(book_path) as book:
        book.run_macro(MACRO_NAME)
    logger.info("マクロを実行: %s", MACRO_NAME)

    # 4. できた結果を配る。
    delivered = copy_file(WORK_FOLDER / OUTPUT_NAME, DELIVERY_FOLDER / OUTPUT_NAME)
    logger.info("配布しました: %s", delivered)


if __name__ == "__main__":
    main()
