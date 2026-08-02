"""
secure_page.py — ログイン後のセキュアエリア画面
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from comken.browser import Locator

from .app_page import AppPage

if TYPE_CHECKING:
    from .login_page import LoginPage


class SecurePage(AppPage):
    """ログイン後のセキュアエリア画面（/secure）。"""

    HEADING = Locator.css("h2")
    LOGOUT_BTN = Locator.css(".button.secondary.radius")

    def get_heading(self) -> str:
        """画面の見出しテキストを返す。"""
        return self.text(self.HEADING)

    def logout(self) -> LoginPage:
        """ログアウトして LoginPage を返す。"""
        from .login_page import LoginPage  # ランタイム用

        self.click(self.LOGOUT_BTN)
        return LoginPage(self.session)
