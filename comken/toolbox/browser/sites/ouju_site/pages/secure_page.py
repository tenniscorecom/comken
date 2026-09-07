"""comken/toolbox/browser/sites/ouju_site/pages/secure_page.py — ログイン後の画面（雛形）

URL や要素セレクタは example の値のまま。利用プロジェクト側で継承して書き換える。
"""

# TYPE_CHECKING 内の LoginPage を型注釈で使うため、注釈の評価を遅延する。
from __future__ import annotations

from typing import TYPE_CHECKING

from comken.toolbox.browser import Locator
from comken.toolbox.browser.sites.ouju_site.pages.app_page import AppPage

if TYPE_CHECKING:
    from comken.toolbox.browser.sites.ouju_site.pages.login_page import LoginPage


class SecurePage(AppPage):
    """ログイン後のセキュアエリア画面（雛形）。"""

    HEADING = Locator.css("h1")
    LOGOUT_BTN = Locator.css("button.logout")

    def get_heading(self) -> str:
        """画面の見出しテキストを返す。"""
        return self.read_text(self.HEADING)

    def logout(self) -> LoginPage:
        """ログアウトして LoginPage を返す。"""
        from comken.toolbox.browser.sites.ouju_site.pages.login_page import LoginPage

        self.click(self.LOGOUT_BTN)
        return self.to(LoginPage)
