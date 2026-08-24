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
    LOCAL_HANDLER_NAME,
    LOG_FORMAT,
    _compute_root_level,
    _guard_root_handlers,
    _warn_external_handlers_allowed,
)


def setup_local_logging(
    *,
    console_level: int = logging.INFO,
    file_level: int = logging.INFO,
    path: str | Path | None = None,
    allow_existing: bool = False,
) -> None:
    """ローカル実行用に root logger を設定する。

    ``path`` はファイル名ではなく保存先フォルダ。省略時は ``project_dir()`` で
    起動スクリプトのプロジェクトを求め、その ``logs`` を使う。``setup_logging()`` の
    直後（root に console と environment ファイルだけがある状態）でも、
    ``setup_logging()`` と組み合わせず単独でも呼べる。``setup_logging()`` 直後なら
    console を使い回して local ファイルだけを追加し、単独なら console と local
    ファイルの 2 種を追加する。

    ``setup_logging()`` と ``setup_local_logging()`` が両方走った状態や、関係のない
    handler が混ざっている場合は ``LoggingAlreadyConfiguredError`` を送出して
    二重出力を防ぐ。comken 以外（他ライブラリ由来）の handler が混ざっている場合は
    ``LoggingConflictError`` を送出し、既存 handler の出力先やレベルを勝手に
    変えてしまうことを防ぐ。``allow_existing=True`` を指定すると、その判定を
    **警告ログだけ**に留めて処理を続行する。
    """
    root_logger = logging.getLogger()
    existing = root_logger.handlers[:]
    external_allowed = _guard_root_handlers(
        existing, side="local", allow_existing=allow_existing
    )

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

    if ENVIRONMENT_HANDLER_NAME in {h.name for h in existing}:
        # setup_logging() が作った console を使い回し、同じログが画面へ2回出るのを防ぐ。
        console_handler = next(h for h in existing if h.name == CONSOLE_HANDLER_NAME)
    else:
        # setup_local_logging() 単独で呼ばれた場合だけ、画面表示用の console も用意する。
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

    # 警告は comken の handler を root に追加し終えてから出す。先に出すと
    # 警告が comken のログファイルに残らず、何と共存したか追跡できなくなる。
    if external_allowed:
        _warn_external_handlers_allowed("setup_local_logging()", existing)
