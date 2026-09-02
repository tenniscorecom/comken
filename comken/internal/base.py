"""comken/internal/base.py — 社内ライブラリの import 失敗時に送出する例外の変換ヘルパー。

社内ライブラリは LAN 環境だけに存在する前提なので、 ``from example_libs import rpa``
のような**静的 import** を ``try / except`` で囲み、 ``raise_if_target_missing()``
で ``ModuleNotFoundError`` を ``InternalLibraryNotFoundError`` に変換する。
動的 import（``importlib`` ベース）にしないのは、pyright の型検査・IDE 補完が
効くこと、 初級エンジニアにも素直に読めることを優先するため。
"""

from __future__ import annotations

from comken.internal.exceptions import InternalLibraryNotFoundError


def raise_if_target_missing(library_name: str, exc: ModuleNotFoundError) -> None:
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
    missing_name = exc.name
    if not missing_name:
        return False
    if missing_name == library_name:
        return True
    return library_name.startswith(missing_name + ".")
