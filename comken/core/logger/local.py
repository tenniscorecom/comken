"""comken/core/logger/local.py — 単体実行用の root logger 構築。

RPA 基盤外で単体実行するとき、各モジュールの logger が同じ出力先を使えるよう
root logger を設定する。
"""

import logging
import os
from pathlib import Path

from comken.core.clock import today
from comken.core.files.ops import project_dir
from comken.core.logger.environment import (
    CONSOLE_HANDLER_NAME,
    DATE_FORMAT,
    ENVIRONMENT_HANDLER_NAME,
    LOG_FORMAT,
)
from comken.exceptions import LoggingAlreadyConfiguredError

LOCAL_HANDLER_NAME = "comken.local"


def local(
    *,
    console_level: int = logging.INFO,
    file_level: int = logging.INFO,
    path: str | Path | None = None,
) -> None:
    """ローカル実行用に root logger を設定する。

    ``path`` はファイル名ではなく保存先フォルダ。省略時は ``project_dir()`` で
    起動スクリプトのプロジェクトを求め、その ``logs`` を使う。``setup()`` の直後なら
    console handler を再利用して local file handler だけを足す。それ以外の設定済み状態は、
    二重出力や出力先の取り違えを防ぐため ``LoggingAlreadyConfiguredError`` にする。
    """
    # setup() と同じrootへ追加することで、利用側は環境を意識せず
    # ``logging.getLogger(__name__)`` で取得したloggerを使い続けられる。
    root_logger = logging.getLogger()
    existing_handlers = root_logger.handlers[:]
    has_environment_handlers = _has_environment_handlers(existing_handlers)
    if existing_handlers and not has_environment_handlers:
        raise LoggingAlreadyConfiguredError()

    project_path = project_dir()
    log_path = Path(path) if path is not None else project_path / "logs"
    if not log_path.is_absolute():
        log_path = project_path / log_path
    log_path.mkdir(parents=True, exist_ok=True)
    log_path /= f"local-{today().isoformat()}.log"

    # environment と同じ本文形式にし、同時実行時も PID でログを見分けられるようにする。
    formatter = logging.Formatter(
        LOG_FORMAT,
        datefmt=DATE_FORMAT,
        defaults={"pid": os.getpid()},
    )
    local_file_handler = logging.FileHandler(log_path, encoding="utf-8")
    local_file_handler.set_name(LOCAL_HANDLER_NAME)
    local_file_handler.setLevel(file_level)
    local_file_handler.setFormatter(formatter)

    if has_environment_handlers:
        # setup() が作ったconsoleを使い回し、同じログが画面へ2回出るのを防ぐ。
        console_handler = next(
            handler for handler in existing_handlers if handler.name == CONSOLE_HANDLER_NAME
        )
        console_handler.setLevel(console_level)
    else:
        # local() 単独で呼ばれた場合だけ、画面表示用のconsoleも用意する。
        console_handler = logging.StreamHandler()
        console_handler.set_name(CONSOLE_HANDLER_NAME)
        console_handler.setLevel(console_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    root_logger.addHandler(local_file_handler)
    # root logger 自身で handler が受け取るログを落とさないよう、低い方まで通す。
    root_logger.setLevel(min(handler.level for handler in root_logger.handlers))


def _has_environment_handlers(handlers: list[logging.Handler]) -> bool:
    """setup() 直後のHandler構成か返す。

    Handlerのクラスを増やさず、標準Handlerへ付けた名前だけで役割を見分ける。
    2個以外ならlocal追加済みか外部設定が混ざっているためFalseにする。
    """
    if len(handlers) != 2:
        return False
    handler_names = {handler.name for handler in handlers}
    return handler_names == {CONSOLE_HANDLER_NAME, ENVIRONMENT_HANDLER_NAME}
