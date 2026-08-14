"""comken/toolbox/browser/management/startup.py — Edgeの起動と初期化を担う

起動に失敗した場合のドライバー更新もここで扱う。
"""

import inspect
import logging
import os
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service

from comken.exceptions import DriverStartError

from ..download import DownloadDir
from ..driver import update_driver
from ..options import BrowserOptions

logger = logging.getLogger(__name__)

START_RETRY_COUNT = 1


def create_service(driver_path: Path, suppress_logs: bool) -> Service:
    """Seleniumの版に合うログ指定でEdgeDriverのServiceを作る。"""
    kwargs: dict[str, str] = {"executable_path": str(driver_path)}
    if suppress_logs:
        # Selenium 4.11で引数名が変わったため、社内に残る旧版にも合わせる。
        parameter_names = inspect.signature(Service).parameters
        log_argument = "log_output" if "log_output" in parameter_names else "log_path"
        kwargs[log_argument] = os.devnull
    return Service(**kwargs)


def start_driver(
    options_config: BrowserOptions,
    profile_dir: Path | None,
    download_dir: DownloadDir,
) -> webdriver.Edge:
    """Edgeを起動し、必要な場合だけドライバー更新後に一度再試行する。"""
    driver_path = Path(options_config.DRIVER_PATH)
    source_dir = options_config.DRIVER_SOURCE_DIR

    for attempt in range(START_RETRY_COUNT + 1):
        try:
            return _build_driver(driver_path, options_config, profile_dir, download_dir)
        except Exception as error:
            is_last_attempt = attempt == START_RETRY_COUNT
            if is_last_attempt or source_dir is None:
                download_dir.__exit__(None, None, None)
                raise DriverStartError(str(driver_path), error) from error

            logger.warning("ブラウザの起動に失敗しました。ドライバーの更新を試みます: %s", error)
            try:
                is_updated = update_driver(driver_path, Path(source_dir))
            except Exception as update_error:
                download_dir.__exit__(None, None, None)
                raise DriverStartError(str(driver_path), update_error) from error
            if not is_updated:
                download_dir.__exit__(None, None, None)
                raise DriverStartError(str(driver_path), error) from error

    raise AssertionError("unreachable")


def _build_driver(
    driver_path: Path,
    options_config: BrowserOptions,
    profile_dir: Path | None,
    download_dir: DownloadDir,
) -> webdriver.Edge:
    """起動オプションを組み立て、初期化済みのEdgeを返す。"""
    edge_options = Options()
    for argument in options_config.build(profile_dir):
        edge_options.add_argument(argument)

    if options_config.SUPPRESS_EXTERNAL_LOGS:
        edge_options.add_experimental_option("excludeSwitches", ["enable-logging"])
        edge_options.add_argument("--log-level=3")
    edge_options.add_experimental_option(
        "prefs",
        {
            "download.default_directory": str(download_dir.path),
            "download.prompt_for_download": False,
        },
    )

    service = create_service(driver_path, options_config.SUPPRESS_EXTERNAL_LOGS)
    driver = webdriver.Edge(service=service, options=edge_options)
    try:
        # 暗黙的待機と明示的待機が重なると、実際の待ち時間が読めなくなる。
        driver.implicitly_wait(0)
    except Exception:
        try:
            driver.quit()
        except Exception:
            logger.warning("初期化に失敗したブラウザを閉じられませんでした", exc_info=True)
        raise
    return driver
