"""
main.py — エントリポイント

このプロジェクトの入口。`python main.py` で実行できる（非エンジニアは 実行.bat をダブルクリック）。

処理の本体は src/ 以下に書き、ここでは「実行 → エラーの受け止め」だけを行う。
"""

import logging

from comken import config
from comken.exceptions import OriginalLibsError

from src.run import run

logger = logging.getLogger(__name__)


def main() -> None:
    # config.SECTION.KEY で config.ini（このフォルダ）の値にアクセスできる。
    # config.REPORT. まで打つと Pylance で補完が出る（typings スタブは自動生成）。
    # 例: 出力先フォルダを取り出す（config.ini の [REPORT] OUTPUT_FOLDER）
    output_folder = config.REPORT.OUTPUT_FOLDER
    logger.info("出力先: %s", output_folder)

    run(output_folder)


if __name__ == "__main__":
    # ログの設定は社内の共通ライブラリ側で行う。ここでは logging をそのまま使う
    # 動作確認だけしたいときは保存・送信をスキップできる:
    #   from comken import set_dry_run; set_dry_run(True)
    try:
        main()
    except OriginalLibsError as e:
        # comken のエラーはメッセージに対処法が入っている（docs/ERRORS.md も参照）
        logger.error("処理を中断しました: %s", e)
        raise
    except Exception:
        logger.error("予期しないエラーが発生しました", exc_info=True)
        raise
