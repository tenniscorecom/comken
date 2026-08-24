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
    LOCAL_HANDLER_NAME,
    LOG_FORMAT,
    _compute_root_level,
    _existing_state,
)
from comken.exceptions import LoggingAlreadyConfiguredError


def local(
    *,
    console_level: int = logging.INFO,
    file_level: int = logging.INFO,
    path: str | Path | None = None,
) -> None:
    """ローカル実行用に root logger を設定する。

    ``path`` はファイル名ではなく保存先フォルダ。省略時は ``project_dir()`` で
    起動スクリプトのプロジェクトを求め、その ``logs`` を使う。``setup()`` の
    直後（root に console と environment ファイルだけがある状態）でも、``setup()``
    と組み合わせず単独でも呼べる。``setup()`` 直後なら console を使い回して
    local ファイルだけを追加し、単独なら console と local ファイルの 2 種を追加する。
    ``setup()`` と ``local()`` が両方走った状態や、関係のない handler が混ざって
    いる場合は ``LoggingAlreadyConfiguredError`` を送出して二重出力を防ぐ。
    """
    root_logger = logging.getLogger()
    existing = root_logger.handlers[:]
    has_environment, _, has_both = _existing_state(existing)

    if has_both:
        # setup() と local() が両方走った後に再度 local() を呼ぶと、
        # 環境ファイルとローカルファイルが二重になる。Console は使い回すので
        # 3 回目以降は確実に「3 つ目を足す」操作になる。
        raise LoggingAlreadyConfiguredError()
    if existing and not has_environment:
        # 関係のない handler（外部ライブラリ等）が混ざっている、または
        # 既に local() が走った後に再度 local() を呼んでいる。
        # 上書きすると既存 handler の出力先やレベルを変えてしまうので止める。
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

    if has_environment:
        # setup() が作った console を使い回し、同じログが画面へ2回出るのを防ぐ。
        console_handler = next(h for h in existing if h.name == CONSOLE_HANDLER_NAME)
    else:
        # local() 単独で呼ばれた場合だけ、画面表示用の console も用意する。
        console_handler = logging.StreamHandler()
        console_handler.set_name(CONSOLE_HANDLER_NAME)
        console_handler.setLevel(console_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    console_handler.setLevel(console_level)
    root_logger.addHandler(local_file_handler)
    # 自分が付けた handler の低い方まで root を通す。root に既に付いている
    # 他者の handler は対象に含めない — 外部の NOTSET(0) ハンドラーが混ざると
    # min が 0 を返し、root まで NOTSET に巻き戻されて isEnabledFor() が
    # DEBUG まで通す穴になるため。
    root_logger.setLevel(_compute_root_level(root_logger.handlers))
