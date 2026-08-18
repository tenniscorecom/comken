"""comken/core/logger.py — 単体実行するプロジェクト向けのログ設定。"""

import logging

from comken.core.clock import today
from comken.core.files.ops import project_dir
from comken.core.logging_run_id import RunIdFilter
from comken.runtime import is_debug

__all__ = ["setup_logging"]

# 出す場所は **カレントではなくプロジェクトのフォルダ**（main.py の場所）。
# 社内 RPA 基盤は C:\ など別の場所をカレントにして呼ぶので、カレント基準だと
# C:\logs\ に書いてしまう。module 読み込み時ではなく、呼ぶ時に決める
LOG_DIR_NAME = "logs"
# ``[RUN:xxxxx]`` は ``RunIdFilter`` が LogRecord に ``run_id`` を入れるため
# に必要。run_id 未設定のときは ``"-"`` が出るので、フォーマット位置は常に揃う
LOG_FORMAT = "[RUN:%(run_id)s] %(asctime)s %(levelname)s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(to_file: bool = True) -> None:
    """単体実行向けに、コンソールと日付別ファイルへのログ出力を設定する。

    社内 RPA 基盤がログを設定する実行では呼び出す必要はない。すでに root logger に
    ハンドラがある場合は、既存の出力先・書式・レベルを変更せず、そのまま返る。

    Args:
        to_file: True なら ``logs/YYYY-MM-DD.log`` にも UTF-8 で出力する。
    """
    root_logger = logging.getLogger()
    # RPA 基盤や利用側が設定済みなら、その出力先・書式・レベルを壊さないため何もしない。
    if root_logger.handlers:
        return

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    # run_id を LogRecord に注入するフィルター。format string が ``%(run_id)s``
    # を要求するので、ハンドラへ必ず付ける
    run_id_filter = RunIdFilter()
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if to_file:
        log_dir = project_dir() / LOG_DIR_NAME
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{today().isoformat()}.log"
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))

    for handler in handlers:
        handler.setFormatter(formatter)
        handler.addFilter(run_id_filter)
        root_logger.addHandler(handler)

    # 詳細な処理時間を調べるデバッグモードでは、DEBUG ログも見えるようにする。
    root_logger.setLevel(logging.DEBUG if is_debug() else logging.INFO)
