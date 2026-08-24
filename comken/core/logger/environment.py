"""comken/core/logger/environment.py — 社内環境向けの root logger 構築。

アプリ全体のログを集めるため root logger を設定する。二重 handler は同じメッセージを
重複出力するため、設定済みなら上書きせず例外にする。保存先は端末名（小文字化して照合）を
``LOG_FOLDER_NAMES`` から引き、日付ごとのファイルとコンソールへ同じ形式で出力する。
``LOG_FOLDER_NAMES`` に登録がない端末は ``LOG_ROOT/_etc_`` へまとめる。
"""

import logging
import os
import socket
from pathlib import Path

from comken.core.clock import today
from comken.core.logger.site import LoggerSite
from comken.exceptions import LoggingAlreadyConfiguredError, LogRootNotConfiguredError

LOG_FORMAT = "%(asctime)s %(levelname)s [pid=%(pid)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
CONSOLE_HANDLER_NAME = "comken.console"
ENVIRONMENT_HANDLER_NAME = "comken.environment"
LOCAL_HANDLER_NAME = "comken.local"
ETC_FOLDER_NAME = "_etc_"
# comken が root に付けた handler だけレベル集計の対象にする。
# 外部の NOTSET ハンドラーが混ざると root が NOTSET に巻き戻され、
# isEnabledFor() が DEBUG まで通す穴になるため (回帰テスト #10)。
COMKEN_HANDLER_NAMES = frozenset(
    {CONSOLE_HANDLER_NAME, ENVIRONMENT_HANDLER_NAME, LOCAL_HANDLER_NAME}
)


def _compute_root_level(handlers: list[logging.Handler]) -> int:
    """comken 管理下の handler のうち最も低いレベルを返す。"""
    levels = [h.level for h in handlers if h.name in COMKEN_HANDLER_NAMES]
    return min(levels) if levels else logging.INFO


def _existing_state(
    handlers: list[logging.Handler],
) -> tuple[bool, bool, bool]:
    """既存 handler の構成を分類する。

    Returns:
        (has_environment_only, has_local_only, has_both):
            has_environment_only: {console, environment} だけ（setup() 直後の状態）
            has_local_only: {console, local} だけ（local() 直後の状態）
            has_both: environment と local が両方ある状態
    """
    names = {h.name for h in handlers}
    if ENVIRONMENT_HANDLER_NAME in names and LOCAL_HANDLER_NAME in names:
        return False, False, True
    if names == {CONSOLE_HANDLER_NAME, ENVIRONMENT_HANDLER_NAME}:
        return True, False, False
    if names == {CONSOLE_HANDLER_NAME, LOCAL_HANDLER_NAME}:
        return False, True, False
    return False, False, False


def setup(site: type[LoggerSite]) -> None:
    """site の指定に従い root logger を設定する。

    PID は同じ端末で同時に動くプロセスを見分ける値であり、保存先を選ぶ端末名とは
    用途が異なる。Formatter の固定値として渡し、ログ呼び出し側へ負担を増やさない。

    ``local()`` が先に走っている場合（root に console と local ファイルだけがある
    場合）は console を再利用し、environment ファイルだけを追加する。逆順（setup() が
    先）では通常どおり console と environment ファイルを追加する。両方がすでに
    走っている、または関係のない handler が混ざっている場合は ``LoggingAlreadyConfiguredError``
    を送出して、二重出力や出力先の取り違えを防ぐ。
    """
    root_logger = logging.getLogger()
    existing = root_logger.handlers[:]
    _, has_local, has_both = _existing_state(existing)

    if has_both:
        # setup() と local() が両方走った後に再度走ると、ログが画面と各ファイルに
        # 二重に出たり、出力先がどちらのルールに従うのか曖昧になる。
        raise LoggingAlreadyConfiguredError()
    if existing and not has_local:
        # 関係のない handler（外部ライブラリ等）が混ざっている、または
        # setup() 直後の状態でさらに setup() を呼んでいる。
        # 上書きすると既存 handler の出力先やレベルを変えてしまうので止める。
        raise LoggingAlreadyConfiguredError()

    site.check_owner()
    # ファイルを作る前に止める。空のフォルダが現場へ残ると
    # 「設定し忘れか、運用で消すのか」が判断できなくなるため。
    if not site.LOG_ROOT:
        raise LogRootNotConfiguredError(site)
    # 登録は大文字／小文字どちらでもよく、運用取得側も大小揺れるので
    # キー側も問い合わせ側も小文字化した上で照合する。
    hostname = socket.gethostname().lower()
    folder_name = next(
        (value for key, value in site.LOG_FOLDER_NAMES.items() if key.lower() == hostname),
        None,
    )
    # 未登録、または値にパス区切りが含まれている場合は _etc_ 扱い。
    # 後者は Path の `/` 演算子が絶対パス値を見ると LOG_ROOT を捨てて
    # 別の場所へ書き込む罠なので、未登録としてガードする。
    if not folder_name or "/" in folder_name or "\\" in folder_name:
        folder_name = ETC_FOLDER_NAME
    log_dir = Path(site.LOG_ROOT) / folder_name
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{site.NAME}-{today().isoformat()}.log"

    formatter = logging.Formatter(
        LOG_FORMAT,
        datefmt=DATE_FORMAT,
        defaults={"pid": os.getpid()},
    )

    if has_local:
        # local() が既に console を備えている。console は使い回して environment
        # ファイルだけを追加する（重複出力を避ける）。console のレベルは
        # local() が決めた値をそのまま使う。
        console_handler = next(h for h in existing if h.name == CONSOLE_HANDLER_NAME)
    else:
        console_handler = logging.StreamHandler()
        console_handler.set_name(CONSOLE_HANDLER_NAME)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    environment_file_handler = logging.FileHandler(log_path, encoding="utf-8")
    environment_file_handler.set_name(ENVIRONMENT_HANDLER_NAME)
    environment_file_handler.setLevel(logging.INFO)
    environment_file_handler.setFormatter(formatter)
    root_logger.addHandler(environment_file_handler)

    root_logger.setLevel(_compute_root_level(root_logger.handlers))
