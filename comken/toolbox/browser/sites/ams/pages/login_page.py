"""comken/toolbox/browser/sites/ams/pages/login_page.py — ログイン画面（AMS の雛形）

URL や要素セレクタは example の値のまま。利用プロジェクト側で継承して書き換える。
"""

# TYPE_CHECKING 内の SecurePage を型注釈で使うため、注釈の評価を遅延する。
from __future__ import annotations

from typing import TYPE_CHECKING

from comken.toolbox.browser import Locator
from comken.toolbox.browser.sites.ams.pages.app_page import AppPage

if TYPE_CHECKING:
    # IDE の補完・型チェック用。ランタイムでは import されない
    from comken.toolbox.browser.sites.ams.pages.change_password_page import ChangePasswordPage
    from comken.toolbox.browser.sites.ams.pages.secure_page import SecurePage


class LoginPage(AppPage):
    """ログイン画面（/login）。"""

    # ── セレクター（F12 で確認した値をここに書く。画面変更時はここだけ直す） ──
    PATH = "/login"
    USERNAME = Locator.id("username")
    PASSWORD = Locator.id("password")
    LOGIN_BTN = Locator.css("button[type=submit]")
    ERROR_MSG = Locator.css(".login-error")

    def login(self, username: str, password: str) -> SecurePage | ChangePasswordPage:
        """ログインして SecurePage を返す。

        パスワードの有効期限切れの場合はサイト側が強制的に変更画面へ飛ばすため、
        代わりに ChangePasswordPage を返す。呼び出し側は型で分岐する:

            result = login_page.login("user", "pass")
            if isinstance(result, ChangePasswordPage):
                from comken.toolbox.credentials import prompt_new_password, save_credential

                new_password = prompt_new_password()
                secure = result.submit_new_password(new_password)   # サイト側へ反映
                # site は login_page.session.name（リテラルの "ams" ではなく）、field は
                # ChangePasswordPage.CREDENTIAL_FIELD を使う。ログイン時に読む側と
                # 書き戻す側で別々に文字列を書くと、typo で別項目として保存され、
                # 次回ログインが古いパスワードのまま失敗し続ける事故につながる。
                save_credential(
                    login_page.session.name,
                    ChangePasswordPage.CREDENTIAL_FIELD,
                    new_password,
                )  # DPAPI側へ反映
            else:
                secure = result
            print(secure.get_heading())

        検知方法（サイトによって挙動が違うので、実際に確かめて選ぶ）:
          1. **URL が変わる**（例: /login → /change-password）。最も多いパターンで、
             ログインボタンを押した後の current_url を見るだけで判定できる。
             既定はこちら。
          2. **URL は変わらず、画面内に変更フォームだけが現れる**（SPA 等、/login の
             まま応答が差し替わる場合）。この場合は URL では判定できないので、
             ``self.has_element(ChangePasswordPage.NEW_PASSWORD)``
             のように変更画面固有の要素の有無で判定する形に書き換える。
        """
        from comken.toolbox.browser.sites.ams.pages.change_password_page import (
            ChangePasswordPage,
        )
        from comken.toolbox.browser.sites.ams.pages.secure_page import SecurePage

        self.input(self.USERNAME, username)
        self.input(self.PASSWORD, password)
        self.click(self.LOGIN_BTN)
        if ChangePasswordPage.PATH in self.session.current_url:
            return self.to(ChangePasswordPage)
        return self.to(SecurePage)

    def get_error_message(self) -> str:
        """ログイン失敗時のエラーメッセージを返す。"""
        return self.read_text(self.ERROR_MSG)
