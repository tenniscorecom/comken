"""単体実行用の名前付き logger 構築。"""

import logging
from pathlib import Path

from comken.core.clock import today
from comken.core.files.ops import project_dir
from comken.core.logger._env import DATE_FORMAT, LOG_FORMAT
from comken.core.logger._run_id import RunIdFilter, install_run_id


def setup_local_logging(
    *,
    console_level: int,
    file_level: int,
    path: str | Path | None,
) -> logging.Logger:
    """ローカル実行用 logger を作成して返す。"""
    project_path = project_dir()
    logger = logging.getLogger(f"comken.local.{project_path.name}")
    for existing_handler in logger.handlers[:]:
        logger.removeHandler(existing_handler)
        existing_handler.close()
    logger.setLevel(min(console_level, file_level))
    logger.propagate = False
    install_run_id()

    log_path = Path(path) if path is not None else project_path / "logs"
    # path はファイルではなく保存先フォルダとして扱う。
    log_path.mkdir(parents=True, exist_ok=True)
    log_path /= f"local-{today().isoformat()}.log"

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    run_id_filter = RunIdFilter()
    handlers: list[tuple[logging.Handler, int]] = [
        (logging.StreamHandler(), console_level),
        (logging.FileHandler(log_path, encoding="utf-8"), file_level),
    ]
    for handler, level in handlers:
        handler.setLevel(level)
        handler.setFormatter(formatter)
        handler.addFilter(run_id_filter)
        logger.addHandler(handler)
    return logger
