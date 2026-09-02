"""comken/toolbox/rpa.py — 社内 RPA 基盤呼び出しの薄いラッパー。

``example_libs.rpa`` を静的 import で読み込み、対象が見つからない場合は
``InternalLibraryNotFoundError`` に変換する。呼び出し自体は
``comken.core.runner.run`` に任せる。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from comken.core.runner import run
from comken.core.timer import measure
from comken.exceptions.rpa import InternalLibraryNotFoundError

RPA_LIBRARY_NAME = "example_libs.rpa"


def _raise_if_target_missing(library_name: str, exc: ModuleNotFoundError) -> None:
    """``library_name`` 自体（またはその親パッケージ）が見つからない場合だけ
    ``InternalLibraryNotFoundError`` に変換して送出する。

    モジュール内部の別の依存が見つからないだけの場合は何もしない
    （呼び出し元がそのまま ``raise`` で元の例外を伝搬させる）。

    判定は ``ModuleNotFoundError.name`` を基準にする:
    - 要求した ``library_name`` そのものが見つからない
    - ``library_name`` の親部分（``library_name.startswith(missing_name + '.')``）
      が見つからない

    その他の依存不足は「対象ライブラリの問題ではない」としてそのまま呼び出し側へ
    伝える。 存在しない親パッケージと内部依存の不足を同じ例外に混ぜると、
    内部依存が壊れただけのときに「社内ライブラリが見つからない」と誤誘導するため、
    ``exc.name`` を直接見て区別する。
    """
    if _is_target_or_parent_missing(library_name, exc):
        raise InternalLibraryNotFoundError(library_name) from exc


def _is_target_or_parent_missing(library_name: str, exc: ModuleNotFoundError) -> bool:
    """``library_name`` 自体またはその親パッケージが見つからないとき True。"""
    missing_name = getattr(exc, "name", None)
    if not missing_name:
        return False
    if missing_name == library_name:
        return True
    return library_name.startswith(missing_name + ".")


@measure
def backoffice(main: Callable[[], Any], project_name: str) -> Any:
    """バックオフィスの RPA として main を実行する。"""
    try:
        # 社内 LAN にだけ存在する（自宅PC・CI では未インストール）
        from example_libs import rpa  # type: ignore[reportMissingImports]
    except ModuleNotFoundError as exc:
        _raise_if_target_missing(RPA_LIBRARY_NAME, exc)
        raise
    return run(f"backoffice で {project_name}", lambda: rpa.backoffice.rpta(main, project_name))


@measure
def intranet(main: Callable[[], Any], project_name: str) -> Any:
    """イントラネットの RPA として main を実行する。"""
    try:
        # 社内 LAN にだけ存在する（自宅PC・CI では未インストール）
        from example_libs import rpa  # type: ignore[reportMissingImports]
    except ModuleNotFoundError as exc:
        _raise_if_target_missing(RPA_LIBRARY_NAME, exc)
        raise
    return run(f"intranet で {project_name}", lambda: rpa.intranet.rpta(main, project_name))


__all__ = ["backoffice", "intranet", "RPA_LIBRARY_NAME"]
