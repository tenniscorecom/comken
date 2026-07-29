"""社内 RPA 基盤（backoffice / intranet）の呼び出しをまとめる。

社内ライブラリはバージョンが import パスに入っている:

    from 社内ライブラリ名.vXXXX.rpa import backoffice

これを各プロジェクトに直接書くと、バージョンが上がるたびに全プロジェクトの
import 行を書き換えることになる。comken は共有サーバー上の1か所を
PYTHONPATH で参照する運用なので、**ここで吸収すれば comken を差し替えるだけで
全プロジェクトが追随する**。

使い方は docs/機能カタログ.md を参照。
"""

import importlib
import logging
from collections.abc import Callable
from types import ModuleType
from typing import Any

from .exceptions import RpaLibraryNotFoundError

logger = logging.getLogger(__name__)

# 社内ライブラリのパッケージ名とバージョン。
# このリポジトリは公開しているため実名は書かない。**共有サーバーへ配置するときに
# この2行を実際の値へ書き換える**（バージョンが上がったときもここだけ直せばよい）。
LIB_ROOT = "internal_rpa_libs"
LIB_VERSION = "v0000"


def _load(name: str) -> ModuleType | Any:
    """社内ライブラリから backoffice / intranet を読み込む。

    Raises:
        RpaLibraryNotFoundError: 社内ライブラリが見つからない場合。
    """
    package_path = f"{LIB_ROOT}.{LIB_VERSION}.rpa"
    try:
        package = importlib.import_module(package_path)
    except ImportError as e:
        raise RpaLibraryNotFoundError(package_path, e) from e

    # `from ... import backoffice` は、属性でもサブモジュールでも通る。
    # importlib で同じことをするには両方試す必要がある。
    target = getattr(package, name, None)
    if target is not None:
        return target
    try:
        return importlib.import_module(f"{package_path}.{name}")
    except ImportError as e:
        raise RpaLibraryNotFoundError(f"{package_path}.{name}", e) from e


def _prepare(project_name: str) -> None:
    """社内ライブラリの規定にそった前準備をする。

    ログの出力先の指定など、毎回書かされる決まり文句をここに集める。
    ここに足せば、全プロジェクトが comken の差し替えだけで追随する。
    """
    # NOTE: 社内ライブラリのログ出力先の規定が未確認のため、今は何もしない。
    #       書き方が分かったらここに足す（呼び出し側は変更不要）。


def _run(target: str, main: Callable[[], Any], project_name: str) -> Any:
    """社内 RPA 基盤の入口を呼ぶ。"""
    entry = _load(target)
    _prepare(project_name)
    logger.info("%s で %s を開始します", target, project_name)
    return entry.rpta(main, project_name)


def run_backoffice(main: Callable[[], Any], project_name: str) -> Any:
    """バックオフィスの RPA として main を実行する。

    社内ライブラリが設定の初期化と時間計測を行い、main を呼ぶ。
    """
    return _run("backoffice", main, project_name)


def run_intranet(main: Callable[[], Any], project_name: str) -> Any:
    """イントラネットの RPA として main を実行する。

    社内ライブラリが設定の初期化と時間計測を行い、main を呼ぶ。
    """
    return _run("intranet", main, project_name)
