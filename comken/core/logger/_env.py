"""社内環境向けの root logger 構築。"""

import csv
import io
import logging
import socket
from pathlib import Path

from comken.core.clock import today
from comken.core.logger._run_id import RunIdFilter, install_run_id
from comken.core.logger._site import LoggerSite
from comken.exceptions import LoggingAlreadyConfiguredError

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s [run_id=%(run_id)s]: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class CsvFormatter(logging.Formatter):
    """指定された LogRecord 属性をCSVの1行へ整形する。"""

    def __init__(self, fields: tuple[str, ...]) -> None:
        super().__init__()
        self._fields = fields

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        values = [getattr(record, field, "") for field in self._fields]
        output = io.StringIO(newline="")
        csv.writer(output, lineterminator="").writerow(values)
        return output.getvalue()


def setup_environment_logging(site: type[LoggerSite]) -> None:
    """site の指定に従い root logger を設定する。"""
    root_logger = logging.getLogger()
    if root_logger.handlers:
        raise LoggingAlreadyConfiguredError()
    site.check_owner()
    install_run_id()

    log_dir = Path(site.LOG_PATH)
    if site.USE_HOSTNAME:
        log_dir /= socket.gethostname()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{site.NAME}-{today().isoformat()}.log"

    formatter: logging.Formatter
    if site.CSV_FIELDS:
        formatter = CsvFormatter(site.CSV_FIELDS)
    else:
        formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    handlers: list[logging.Handler] = [
        logging.StreamHandler(),
        logging.FileHandler(log_path, encoding="utf-8"),
    ]
    run_id_filter = RunIdFilter()
    for handler in handlers:
        handler.setFormatter(formatter)
        handler.addFilter(run_id_filter)
        root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
