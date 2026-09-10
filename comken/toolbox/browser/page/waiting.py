"""comken/toolbox/browser/page/waiting.py — 表示・非表示を待つ（wait_visible / wait_invisible）。"""

from __future__ import annotations

import logging

from selenium.webdriver.support import expected_conditions as EC

from comken.toolbox.browser.locator import Locator
from comken.toolbox.browser.page.base import _PageBase

logger = logging.getLogger(__name__)


class WaitingMixin(_PageBase):
    """表示・非表示を待つ（wait_visible / wait_invisible）。"""

    def wait_visible(self, locator: Locator) -> None:
        """要素が表示されるまで待つ（画面が開くのを待つときなど）。"""
        logger.debug("要素の表示を待ちます: locator=%s timeout=%d秒", locator, self._wait_seconds)
        with self.session._operating(f"wait_visible({locator})"):
            self._until(EC.visibility_of_element_located(locator), locator, "表示され")
        logger.debug("要素が表示されました: locator=%s", locator)

    def wait_invisible(self, locator: Locator) -> None:
        """要素が消えるまで待つ（読み込み中の表示が消えるのを待つときなど）。"""
        logger.debug("要素の消失を待ちます: locator=%s timeout=%d秒", locator, self._wait_seconds)
        with self.session._operating(f"wait_invisible({locator})"):
            self._until(EC.invisibility_of_element_located(locator), locator, "消え")
        logger.debug("要素が消えました: locator=%s", locator)

    def wait_for_result(self, url_before: str, error_locator: Locator) -> None:
        """フォーム送信の結果が出るまで待つ:「URL が変わる」か「error_locator の
        要素が出る」のどちらか早い方が起きた時点で確定する。

        結果が Ajax 等で少し遅れて出る画面で、送信直後に一度だけ確認すると
        表示の遅れをすり抜けてしまう（実際は失敗しているのに成功と判定して
        しまう）のを防ぐために使う。早い方が起きた時点で確定するので、
        成功時に無駄な待ちは発生しない。

            url_before = self.session.current_url
            self.click(self.LOGIN_BTN)
            self.wait_for_result(url_before, self.ERROR_MSG)
            self.raise_if_shown(self.ERROR_MSG, LoginFailedError)
        """
        with self.session._operating(f"wait_for_result(url_before={url_before!r})"):
            self._until(
                EC.any_of(
                    EC.url_changes(url_before),
                    EC.presence_of_element_located(error_locator),
                ),
                error_locator,
                "結果が確定し",
            )
        logger.debug(
            "結果が確定しました: url_before=%s error_locator=%s", url_before, error_locator
        )
