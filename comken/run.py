"""comken/run.py — RPA 基盤（社内実行環境）からの呼び出し口。

**ローカル（自宅）で動かすための実装。** 社内の実際の ``run`` は、規定のメッセージ
（バックオフィス／イントラネット）を出し、実行時間を計測して ``HH:MM`` で表示してから
``main()`` の結果を返す。ここでも同じ流れ（開始メッセージ → ``main()`` → 終了メッセージと
実行時間）にしてあるが、**メッセージの文言は社内の規定そのものではない**（下の定数）。
ログの設定は呼び出し側（``main.py``）が行うので、ここでは ``logging`` に出すだけ。

    from comken.run import backoffice

    def main() -> None:
        ...

    if __name__ == "__main__":
        backoffice(main, "プロジェクト名")
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from comken.core.calendar import warn_if_calendar_expiring_soon

logger = logging.getLogger(__name__)

# 環境ごとのメッセージ。社内の規定に合わせるときは、ここだけ差し替える。
_BACKOFFICE_LABEL = "バックオフィス"
_INTRANET_LABEL = "イントラネット"
_START_MESSAGE = "【%s】%s を開始します"
_FINISH_MESSAGE = "【%s】%s が終了しました（実行時間 %s）"
_FAILURE_MESSAGE = "【%s】%s が異常終了しました（実行時間 %s）"


def _format_hhmm(seconds: float) -> str:
    """経過秒数を ``HH:MM`` にする（分未満は切り捨て。100 時間を超えても時は桁が増えるだけ）。"""
    total_minutes = int(seconds // 60)
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def _run(main: Callable[[], Any], project_name: str, label: str) -> Any:
    """開始メッセージ → ``main()`` → 終了メッセージと実行時間（``HH:MM``）。

    ``main()`` が例外を出したときも、異常終了のメッセージと実行時間を出してから再送出する。
    """
    warn_if_calendar_expiring_soon()
    logger.info(_START_MESSAGE, label, project_name)
    start = time.perf_counter()
    try:
        result = main()
    except BaseException:
        logger.error(
            _FAILURE_MESSAGE, label, project_name, _format_hhmm(time.perf_counter() - start)
        )
        raise
    logger.info(_FINISH_MESSAGE, label, project_name, _format_hhmm(time.perf_counter() - start))
    return result


def backoffice(main: Callable[[], Any], project_name: str) -> Any:
    """バックオフィスの RPA として ``main`` を実行し、``main()`` の戻り値を返す。

    Args:
        main: 実行する関数。
        project_name: プロジェクト名。開始・終了メッセージに出る。
    """
    return _run(main, project_name, _BACKOFFICE_LABEL)


def intranet(main: Callable[[], Any], project_name: str) -> Any:
    """イントラネットの RPA として ``main`` を実行し、``main()`` の戻り値を返す。

    Args:
        main: 実行する関数。
        project_name: プロジェクト名。開始・終了メッセージに出る。
    """
    return _run(main, project_name, _INTRANET_LABEL)


__all__ = ["backoffice", "intranet"]
