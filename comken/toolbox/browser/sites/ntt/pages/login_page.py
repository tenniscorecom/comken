"""comken/toolbox/browser/sites/ntt/pages/login_page.py — ログイン画面

※ セレクターはダミー。配置するときに実際の画面（F12 で確認した値）へ書き換える。
"""

# TYPE_CHECKING 内の SecurePage を型注釈で使うため、注釈の評価を遅延する。
from __future__ import annotations

from typing import TYPE_CHECKING

from comken.toolbox.browser import Locator
from comken.toolbox.browser.sites.ntt.pages.app_page import AppPage

if TYPE_CHECKING:
    # IDE の補完・型チェック用。ランタイムでは import されない
    from comken.toolbox.browser.sites.ntt.pages.secure_page import SecurePage


class LoginPage(AppPage):
    """ログイン画面（/login）。NTT西・NTT東で共通のセレクター・操作を仮定している。"""

    # ── セレクター（配置時に F12 で確認した実際の値へ書き換える） ──
    USERNAME = Locator.id("username")
    PASSWORD = Locator.id("password")
    LOGIN_BTN = Locator.css(".login-btn")

    def login(self, username: str, password: str) -> SecurePage:
        """ログインして SecurePage（ログイン後の画面）を返す。"""
        from comken.toolbox.browser.sites.ntt.pages.secure_page import SecurePage

        self.input(self.USERNAME, username)
        self.input(self.PASSWORD, password)
        self.click(self.LOGIN_BTN)
        return self.to(SecurePage)
