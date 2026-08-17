"""comken/toolbox/browser/management/tabs.py — タブを開閉する内部管理。

1つのブラウザーセッション内でのみ使う。
"""

import logging
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait

from comken.exceptions import PopupTabNotOpenedError
from comken.toolbox.browser.locator import Locator

logger = logging.getLogger(__name__)

TAB_POLL_INTERVAL_SECONDS = 0.5
NEW_TAB_TIMEOUT_SECONDS = 10


class _TabManager:
    """1つの WebDriver のタブを開閉し、元のタブへ確実に戻す。"""

    def __init__(self, driver: webdriver.Edge, session_name: str) -> None:
        self._driver = driver
        self._session_name = session_name

    @contextmanager
    def popup(self, seconds: int) -> Iterator[None]:
        """新しく開いたタブへ移動し、終了時に閉じて元のタブへ戻る。"""
        original = self._driver.current_window_handle
        self._wait_for_new_tab(original, seconds)
        opened = [handle for handle in self._driver.window_handles if handle != original][-1]
        self._driver.switch_to.window(opened)
        try:
            yield
        finally:
            self._close_popup(opened, original)

    def load_many(
        self, urls: Sequence[str], ready: Locator | None, max_open: int, seconds: int
    ) -> Iterator[str]:
        """URLを複数タブで先に開き、読み込みが終わった順にURLを返す。"""
        original = self._driver.current_window_handle
        waiting = list(urls)
        opened: dict[str, tuple[str, float]] = {}
        try:
            while waiting or opened:
                while waiting and len(opened) < max_open:
                    url = waiting.pop(0)
                    handle = self._open_in_background(url)
                    if handle is not None:
                        opened[handle] = (url, time.monotonic())
                finished = self._take_finished(opened, ready, seconds)
                if finished is None:
                    time.sleep(TAB_POLL_INTERVAL_SECONDS)
                    continue
                handle, url = finished
                self._driver.switch_to.window(handle)
                try:
                    yield url
                finally:
                    del opened[handle]
                    self._close(handle)
        finally:
            for handle in list(opened):
                self._close(handle)
            if original in self._driver.window_handles:
                self._driver.switch_to.window(original)

    def _open_in_background(self, url: str) -> str | None:
        before = set(self._driver.window_handles)
        self._driver.execute_script("window.open(arguments[0], '_blank');", url)
        try:
            WebDriverWait(self._driver, NEW_TAB_TIMEOUT_SECONDS).until(
                lambda driver: set(driver.window_handles) - before
            )
        except TimeoutException:
            logger.warning("タブを開けませんでした（この URL は飛ばします）: %s", url)
            return None
        return next(iter(set(self._driver.window_handles) - before))

    def _take_finished(
        self, opened: dict[str, tuple[str, float]], ready: Locator | None, seconds: int
    ) -> tuple[str, str] | None:
        for handle, (url, started_at) in list(opened.items()):
            if handle not in self._driver.window_handles:
                logger.warning("読み込み中にタブが閉じられました: %s", url)
                del opened[handle]
                continue
            if self._is_loaded(handle, ready):
                return handle, url
            if time.monotonic() - started_at > seconds:
                logger.warning("%s 秒以内に読み込めませんでした（飛ばします）: %s", seconds, url)
                del opened[handle]
                self._close(handle)
        return None

    def _is_loaded(self, handle: str, ready: Locator | None) -> bool:
        try:
            self._driver.switch_to.window(handle)
            if ready is not None:
                return bool(self._driver.find_elements(*ready))
            return self._driver.execute_script("return document.readyState") == "complete"
        except Exception:
            logger.warning("タブの状態を確認できませんでした", exc_info=True)
            return False

    def _close(self, handle: str) -> None:
        try:
            if handle in self._driver.window_handles:
                self._driver.switch_to.window(handle)
                self._driver.close()
        except Exception:
            logger.warning("タブを閉じられませんでした", exc_info=True)

    def _close_popup(self, opened: str, original: str) -> None:
        try:
            if opened in self._driver.window_handles:
                self._driver.close()
            if original in self._driver.window_handles:
                self._driver.switch_to.window(original)
            else:
                logger.warning(
                    "元のタブが閉じられていたため、戻れませんでした: %s",
                    self._session_name,
                )
        except Exception:
            logger.warning("別タブの後始末に失敗しました: %s", self._session_name, exc_info=True)

    def _wait_for_new_tab(self, original: str, seconds: int) -> None:
        try:
            WebDriverWait(self._driver, seconds).until(
                lambda driver: any(handle != original for handle in driver.window_handles)
            )
        except TimeoutException as error:
            raise PopupTabNotOpenedError(seconds) from error
