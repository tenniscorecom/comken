"""
main.py — エントリポイント

このプロジェクトの入口。`実行.bat` か `python main.py` で実行する。

処理の本体は src/ 以下に書き、ここでは「実行 → エラーの受け止め」だけを行う。
社内 RPA 基盤から動かす場合は、下の「社内 RPA 基盤から実行する場合」を参照。
"""

import logging

from comken import config, debug, setup_logging
from comken.exceptions import ComkenError

from src.run import run

logger = logging.getLogger(__name__)


def main() -> None:
    # 設定の読み取りも処理も src/run.py に書く。ここは呼ぶだけにしておく
    run()


if __name__ == "__main__":
    # 単体で動かすので、ログの出力先をここで用意する（コンソールと logs/YYYY-MM-DD.log）。
    setup_logging()
    try:
        # config.ini に必要な項目がそろっているかを最初に確かめる。
        # 途中まで動いてから足りないと分かるより、動き出す前に全部まとめて出す。
        # 使う項目を増やしたらここにも足す（消しても動くが、エラーが遅くなる）
        config.require("FILES.OUTPUT_FOLDER")

        with debug():
            main()
    except ComkenError as e:
        # comken のエラーはメッセージに対処法が入っている（docs/ERRORS.md も参照）
        logger.error("処理を中断しました: %s", e)
        raise
    except Exception:
        logger.error("予期しないエラーが発生しました", exc_info=True)
        raise

# ── 社内 RPA 基盤から実行する場合 ─────────────────────────────────────────────
# **実行.bat を使っても、`python <このフォルダ>\main.py` を直接呼んでもよい。**
# どちらの経路でも `PYTHONPATH` を `実行.bat` が肩代わりするので、基盤側の指定は要らない。
# `実行.bat` は終了コードをそのまま返すので、基盤はそれで成否を判断できる
# （`pause` を入れないのは、無人実行で止まらないようにするため）。
# カレントは C:\ など別の場所になるが、config.ini・logs はこのフォルダを基準に
# 探すので、そのままで動く（comken の project_dir() がその役目）。
#
# 上の `setup_logging()` と `main()` の2行を、次の形に差し替える。
# 基盤が設定の初期化・時間計測・ログ設定をしてから main を呼ぶので、
# setup_logging() は呼ばない（呼んでも二重設定にはならないが、基盤の設定が正になる）。
#
# dry-run / debug を一時的に有効化したい場合は、`main()` を `with dry_run():` /
# `with debug():` で囲む形にする（プロセス全体への setter は用意していない）。
#
#     from comken.toolbox.rpa import backoffice   # イントラネットのツールなら intranet に変える
#
#     PROJECT_NAME = "（プロジェクト名）"   # 基盤へ渡す名前。ログの識別に使われる
#
#     if __name__ == "__main__":
#         try:
#             backoffice(main, PROJECT_NAME)
#         except ComkenError as e:
#             logger.error("処理を中断しました: %s", e)
#             raise
