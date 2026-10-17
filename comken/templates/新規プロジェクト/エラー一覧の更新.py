"""
エラー一覧の更新.py — docs/ERRORS.md のエラー名の表を作り直す

`エラー一覧の更新.bat` か `python エラー一覧の更新.py` で実行する。

src/ で定義した ComkenError のサブクラスと comken のエラーを、docstring から表にする。
エラーを足したり docstring を直したりしたら実行する（手で表を直すと、すぐ古くなるため）。
"""

import logging

from comken import comken_logger
from comken.core.files import project_dir
from comken.exceptions import ComkenError
from comken.tools.errors_doc import update_errors_doc

import src

logger = logging.getLogger(__name__)


def main() -> None:
    """docs/ERRORS.md の自動生成部分を作り直す。"""
    path = project_dir() / "docs" / "ERRORS.md"
    if update_errors_doc(path, project_package=src):
        logger.info("エラー一覧を更新しました: %s", path)
    else:
        logger.info("エラー一覧は最新です: %s", path)


if __name__ == "__main__":
    comken_logger.setup_local_logging()
    try:
        main()
    except ComkenError as e:
        logger.error("処理を中断しました: %s", e)
        raise
