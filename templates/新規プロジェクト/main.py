"""
main.py — エントリポイント

このプロジェクトの入口。`python main.py` で実行できる（非エンジニアは 実行.bat をダブルクリック）。

処理の本体は src/ 以下に書き、ここでは「実行 → エラーの受け止め」だけを行う。
社内 RPA 基盤から動かす場合は、下の「社内 RPA 基盤から実行する場合」を参照。
"""

import logging

from comken import config, dry_run, setup_logging
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
        config.require("RUN.DRY_RUN", "FILES.OUTPUT_FOLDER")

        # config.ini の [RUN] DRY_RUN で切り替える。True の間は書き込み・移動・保存を
        # せず、何をするつもりかだけログに出す。コードを触らずに試せるので、
        # 本番前の確認を非エンジニアだけで回せる。
        #
        # True のまま戻し忘れると「毎日成功しているのに何も出力されない」状態になり、
        # 終了コードも 0 なのでスケジューラからは正常に見える。気づけるように
        # 実行のたび WARNING を出す（INFO は流し読みされるので警告にする）。
        if config.RUN.DRY_RUN:
            logger.warning(
                "DRY-RUN で実行します。ファイルは書き込まれません"
                "（本番で動かすなら config.ini の [RUN] DRY_RUN を False にする）"
            )
        with dry_run(config.RUN.DRY_RUN):
            main()
    except ComkenError as e:
        # comken のエラーはメッセージに対処法が入っている（docs/ERRORS.md も参照）
        logger.error("処理を中断しました: %s", e)
        raise
    except Exception:
        logger.error("予期しないエラーが発生しました", exc_info=True)
        raise

# ── 社内 RPA 基盤から実行する場合 ─────────────────────────────────────────────
# 上の `setup_logging()` と `main()` の2行を、次の形に差し替える。
# 基盤が設定の初期化・時間計測・ログ設定をしてから main を呼ぶので、
# setup_logging() は呼ばない（呼んでも二重設定にはならないが、基盤の設定が正になる）。
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
