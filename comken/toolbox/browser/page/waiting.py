"""comken/toolbox/browser/page/waiting.py — 表示・非表示を待つ（wait_visible / wait_invisible）。"""

from __future__ import annotations

from selenium.webdriver.support import expected_conditions as EC

from comken.toolbox.browser.locator import Locator
from comken.toolbox.browser.page.base import _PageBase


class WaitingMixin(_PageBase):
    """表示・非表示を待つ（wait_visible / wait_invisible）。"""

    def wait_visible(self, locator: Locator) -> None:
        """要素が表示されるまで待つ（画面が開くのを待つときなど）。"""
        with self.session._operating(f"wait_visible({locator})"):
            self._until(EC.visibility_of_element_located(locator), locator, "表示され")

    def wait_invisible(self, locator: Locator) -> None:
        """要素が消えるまで待つ（読み込み中の表示が消えるのを待つときなど）。"""
        with self.session._operating(f"wait_invisible({locator})"):
            self._until(EC.invisibility_of_element_located(locator), locator, "消え")
