"""comken/toolbox/browser/management/startup.py — Edgeの起動と初期化を担う"""

import inspect
import logging
import os
from pathlib import Path
from typing import Any

from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service

from comken.exceptions import DriverStartError
from comken.toolbox.browser.download import DownloadDir
from comken.toolbox.browser.options import BrowserOptions

logger = logging.getLogger(__name__)


def create_service(driver_path: Path, suppress_logs: bool) -> Service:
    """Seleniumの版に合うログ指定でEdgeDriverのServiceを作る。"""
    # dict[str, str] にすると、型チェッカーが「**kwargs はどのパラメータにも str を
    # 渡しうる」と読んで port（int）や env と衝突する。渡すのは下の2つだけ
    kwargs: dict[str, Any] = {"executable_path": str(driver_path)}
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
    """Edgeを起動する。失敗したら一時フォルダを片付けてから例外を送出する。"""
    driver_path = Path(options_config.DRIVER_PATH)
    try:
        return _build_driver(driver_path, options_config, profile_dir, download_dir)
    except Exception as error:
        # 一時フォルダを残さない。download_dir は with 想定だが、__enter__ 失敗時は
        # ここで __exit__ を呼んで後始末する必要がある
        download_dir.__exit__(None, None, None)
        raise DriverStartError(str(driver_path), error) from error


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
