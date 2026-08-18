"""comken/toolbox/browser/sites/sample/pages/secure_page.py — ログイン後のセキュアエリア画面"""

# TYPE_CHECKING 内の LoginPage を型注釈で使うため、注釈の評価を遅延する。
from __future__ import annotations

from typing import TYPE_CHECKING

from comken.toolbox.browser import Locator
from comken.toolbox.browser.sites.sample.pages.app_page import AppPage

if TYPE_CHECKING:
    from comken.toolbox.browser.sites.sample.pages.login_page import LoginPage


class SecurePage(AppPage):
    """ログイン後のセキュアエリア画面（/secure）。"""

    HEADING = Locator.css("h2")
    LOGOUT_BTN = Locator.css(".button.secondary.radius")

    def get_heading(self) -> str:
        """画面の見出しテキストを返す。"""
        return self.read_text(self.HEADING)

    def logout(self) -> LoginPage:
        """ログアウトして LoginPage を返す。"""
        from comken.toolbox.browser.sites.sample.pages.login_page import LoginPage

        self.click(self.LOGOUT_BTN)
        return self.to(LoginPage)
