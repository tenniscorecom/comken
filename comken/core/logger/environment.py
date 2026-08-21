"""comken/core/logger/environment.py — 社内環境向けの root logger 構築。

アプリ全体のログを集めるため root logger を設定する。二重 handler は同じメッセージを
重複出力するため、設定済みなら上書きせず例外にする。保存先は端末名を ``LOG_FOLDERS`` から
引き、日付ごとのファイルとコンソールへ同じ形式で出力する。
"""

import logging
import os
import socket
from pathlib import Path

from comken.core.clock import today
from comken.core.logger.site import LoggerSite
from comken.exceptions import LoggerHostNotConfiguredError, LoggingAlreadyConfiguredError

LOG_FORMAT = "%(asctime)s %(levelname)s [pid=%(pid)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
CONSOLE_HANDLER_NAME = "comken.console"
ENVIRONMENT_HANDLER_NAME = "comken.environment"


def setup(site: type[LoggerSite]) -> None:
    """site の指定に従い root logger を設定する。

    PID は同じ端末で同時に動くプロセスを見分ける値であり、保存先を選ぶ端末名とは
    用途が異なる。Formatter の固定値として渡し、ログ呼び出し側へ負担を増やさない。
    """
    # 各ファイルの ``logging.getLogger(__name__)`` をまとめて受け取るため、
    # 名前付き logger を個別に設定せず、一番上にある root logger を設定する。
    # ``basicConfig()`` はHandlerがあると2回目の設定を黙って無視するため使わない。
    # setup() 後にlocal()のファイルHandlerだけを追加し、BO/Intranetの二重設定は
    # 例外として見つけたいので、Handlerを直接管理する。
    root_logger = logging.getLogger()
    # Handler が重なると同じメッセージが2回出る。既存設定を推測して上書きせず、
    # アプリの入口で setup() を1回だけ呼ぶルールにする。
    if root_logger.handlers:
        raise LoggingAlreadyConfiguredError()

    site.check_owner()
    hostname = socket.gethostname()
    folder = site.LOG_FOLDERS.get(hostname)
    if folder is None:
        raise LoggerHostNotConfiguredError(hostname, site.NAME)
    # Site側は端末名とフォルダ文字列だけを持ち、ファイルを作る直前にPathへ変換する。
    log_dir = Path(folder)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{site.NAME}-{today().isoformat()}.log"

    formatter = logging.Formatter(
        LOG_FORMAT,
        datefmt=DATE_FORMAT,
        defaults={"pid": os.getpid()},
    )

    # consoleは画面表示、environmentは社内環境の標準ファイルを表す。
    # local() が後から呼ばれたとき、この名前で既存consoleを再利用する。
    console_handler = logging.StreamHandler()
    console_handler.set_name(CONSOLE_HANDLER_NAME)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.set_name(ENVIRONMENT_HANDLER_NAME)
    handlers: list[logging.Handler] = [console_handler, file_handler]
    for handler in handlers:
        handler.setLevel(logging.INFO)
        handler.setFormatter(formatter)

    for handler in handlers:
        root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
