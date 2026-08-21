"""1回の実行を識別する run_id の管理。"""

import logging
import os
from contextvars import ContextVar

_run_id_var: ContextVar[str] = ContextVar("comken_run_id", default="")


def install_run_id() -> str:
    """現在のプロセスIDを run_id として設定して返す。"""
    run_id = str(os.getpid())
    _run_id_var.set(run_id)
    return run_id


def current_run_id() -> str:
    """現在の run_id を返す。"""
    return _run_id_var.get()


class RunIdFilter(logging.Filter):
    """LogRecord に現在の run_id を追加する。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = current_run_id()
        return True
