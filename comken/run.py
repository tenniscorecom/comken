"""comken/run.py — RPA 基盤（社内実行環境）からの呼び出し口。

以前は社内 RPA 基盤（外部パッケージ ``kensetsu_libs.rpa``）を呼び出す薄い
ラッパーだったが、社内側の RPA 基盤が再編され、外部パッケージへの依存が
無くなった（内製化された）。**それに伴い、このモジュールは最小実装
（``main()`` を呼ぶだけ）にしている。** 実際のログ設定・実行時間計測などの
処理は社内固有のため comken には持たない。

    from comken.run import backoffice

    def main() -> None:
        ...

    if __name__ == "__main__":
        backoffice(main, "プロジェクト名")
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def backoffice(main: Callable[[], Any], project_name: str) -> Any:
    """バックオフィスの RPA として main を実行する。

    現在は最小実装（``main()`` を呼んで結果を返すだけ）。``project_name`` は
    呼び出し側との呼び出し規約（シグネチャ）を保つために受け取るが、現状では
    使っていない。

    Args:
        main: 実行する関数。
        project_name: プロジェクト名（現状は未使用）。

    Returns:
        ``main()`` の戻り値。
    """
    target_name = getattr(main, "__name__", type(main).__name__)
    logger.debug(
        "バックオフィス RPA として main を実行します: target=%s project_name=%s",
        target_name,
        project_name,
    )
    try:
        result = main()
    except Exception:
        logger.debug(
            "バックオフィス RPA の main 実行が失敗しました: target=%s",
            target_name,
            exc_info=True,
        )
        raise
    logger.debug(
        "バックオフィス RPA の main 実行が完了しました: target=%s",
        target_name,
    )
    return result


def intranet(main: Callable[[], Any], project_name: str) -> Any:
    """イントラネットの RPA として main を実行する。

    現在は最小実装（``main()`` を呼んで結果を返すだけ）。``project_name`` は
    呼び出し側との呼び出し規約（シグネチャ）を保つために受け取るが、現状では
    使っていない。

    Args:
        main: 実行する関数。
        project_name: プロジェクト名（現状は未使用）。

    Returns:
        ``main()`` の戻り値。
    """
    target_name = getattr(main, "__name__", type(main).__name__)
    logger.debug(
        "イントラネット RPA として main を実行します: target=%s project_name=%s",
        target_name,
        project_name,
    )
    try:
        result = main()
    except Exception:
        logger.debug(
            "イントラネット RPA の main 実行が失敗しました: target=%s",
            target_name,
            exc_info=True,
        )
        raise
    logger.debug(
        "イントラネット RPA の main 実行が完了しました: target=%s",
        target_name,
    )
    return result


__all__ = ["backoffice", "intranet"]
