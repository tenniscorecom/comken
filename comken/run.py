"""comken/run.py — 社内 RPA 基盤（backoffice / intranet）の呼び出しをまとめる。

社内ライブラリはバージョンが import パスに入っている:

    from example_libs.v0000.rpa import backoffice

これを各プロジェクトに直接書くと、バージョンが上がるたびに全プロジェクトの
import 行を書き換えることになる。comken は共有サーバー上の1か所を
PYTHONPATH で参照する運用なので、**ここで吸収すれば comken を差し替えるだけで
全プロジェクトが追随する**。

    from comken.run import backoffice   # イントラネット側は intranet

    backoffice(main, "受注取込")

**このリポジトリは公開しているため、社内ライブラリ名は `example_libs.v0000` という
仮の名前にしてある。共有サーバーへ配置するときに、下の2つの関数の import 行を
実際の名前とバージョンへ書き換える。**（バージョンが上がったときも同じ2行を直す）

社内ライブラリの正式版が出てこのファイルが不要になったら、次を消せば完了する
（comken の他のモジュールはこのファイルに依存していない）:

    1. このファイル（comken/run.py）
    2. comken/exceptions/rpa.py と、comken/exceptions/__init__.py の RpaError の記述
    3. tests/test_run.py
    4. ERRORS.md / templates/新規プロジェクト/docs/ERRORS.md / README.md /
       仕様書.md の、社内 RPA 基盤に関する記述

使い方は README.md を参照。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from .exceptions import RpaLibraryNotFoundError

logger = logging.getLogger(__name__)

__all__ = ["backoffice", "intranet"]


def _prepare(project_name: str) -> None:
    """社内ライブラリの規定にそった前準備をする。

    ログの出力先の指定など、毎回書かされる決まり文句をここに集める。
    ここに足せば、全プロジェクトが comken の差し替えだけで追随する。
    """
    # NOTE: 社内ライブラリのログ出力先の規定が未確認のため、今は何もしない。
    #       書き方が分かったらここに足す（呼び出し側は変更不要）。


def _call(entry: Any, target: str, main: Callable[[], Any], project_name: str) -> Any:
    """社内 RPA 基盤の入口を呼ぶ。"""
    _prepare(project_name)
    logger.info("%s で %s を開始します", target, project_name)
    return entry.rpta(main, project_name)


def backoffice(main: Callable[[], Any], project_name: str) -> Any:
    """バックオフィスの RPA として main を実行する。

    社内ライブラリが設定の初期化と時間計測を行い、main を呼ぶ。

    Raises:
        RpaLibraryNotFoundError: 社内ライブラリが読み込めない場合。
    """
    # 社内ライブラリを読むのはこの1行。関数の中に置くのは、社内ライブラリが無い PC でも
    # comken 自体は読み込めるようにするため（テストもここを差し替える）。
    try:
        from example_libs.v0000.rpa import backoffice as entry
    except ImportError as e:
        raise RpaLibraryNotFoundError("example_libs.v0000.rpa.backoffice", e) from e
    return _call(entry, "backoffice", main, project_name)


def intranet(main: Callable[[], Any], project_name: str) -> Any:
    """イントラネットの RPA として main を実行する。

    社内ライブラリが設定の初期化と時間計測を行い、main を呼ぶ。

    Raises:
        RpaLibraryNotFoundError: 社内ライブラリが読み込めない場合。
    """
    try:
        from example_libs.v0000.rpa import intranet as entry
    except ImportError as e:
        raise RpaLibraryNotFoundError("example_libs.v0000.rpa.intranet", e) from e
    return _call(entry, "intranet", main, project_name)
