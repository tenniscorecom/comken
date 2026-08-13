"""comken/windows/process.py — Excel 孤立プロセスの検出・後始末

COM 経由の Excel 自動化は、クラッシュや強制終了で EXCEL.EXE が
画面に見えないまま裏に残ることがある。残った Excel はファイルを
ロックし続け、次回実行時に原因不明のエラーを引き起こす。

自動処理の開始前に呼んで、前回の残骸を片付けるために使う。
"""

import logging
import subprocess

logger = logging.getLogger(__name__)


def is_excel_running() -> bool:
    """EXCEL.EXE プロセスが存在するか返す。

    画面に見えない孤立プロセスも、ユーザーが開いている Excel も区別せず検出する。
    """
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq EXCEL.EXE", "/NH"],
        capture_output=True,
        text=True,
    )
    return "EXCEL.EXE" in result.stdout


def kill_excel() -> bool:
    """すべての EXCEL.EXE プロセスを強制終了する。

    ※ ユーザーが開いている Excel も終了する（未保存の変更は失われる）。
      人が作業する PC では実行前に確認するか、is_excel_running() の警告に留めること。
      無人実行の PC で自動処理の開始前に呼ぶのが主な用途。

    Returns:
        True: 終了に成功した。False: 起動していなかった、または終了に失敗した。
    """
    if not is_excel_running():
        return False
    result = subprocess.run(
        ["taskkill", "/F", "/IM", "EXCEL.EXE"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.warning("EXCEL.EXE プロセスを終了できませんでした: %s", result.stderr.strip())
        return False
    logger.info("EXCEL.EXE プロセスを終了しました（前回処理の残骸の可能性）")
    return True
