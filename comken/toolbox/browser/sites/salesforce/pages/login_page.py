"""comken/toolbox/browser/sites/salesforce/pages/login_page.py — Salesforceのログイン画面。

id="username" / id="password" / id="Login" はSalesforceのログイン画面
（Lightning・Classicどちらのドメインでも同じ）で長年変わっていない標準的なIDで、
Selenium系の自動化事例でも広く使われている。
"""

from __future__ import annotations

import logging

from comken.toolbox.browser import Locator, SitePage

logger = logging.getLogger(__name__)


class LoginPage(SitePage):
    """Salesforceのログイン画面（BASE_URLそのもの）。"""

    USERNAME = Locator.id("username")
    PASSWORD = Locator.id("password")
    LOGIN_BTN = Locator.id("Login")

    def login(self, username: str, password: str) -> None:
        """ID/パスワードを入力してログインボタンを押す。

        MFA（認証コード・端末認証など）が要求されるかどうかは組織の設定次第で
        自動判定できないため、ここでは送信するところまでで、その後の待ち受けは
        呼び出し側の ``Salesforce.wait_for_manual_login()`` に任せる。

        Args:
            username: Salesforceのユーザー名（メールアドレス形式のことが多い）。
            password: パスワード。ログには絶対に出さない。
        """
        logger.info("Salesforceへログインを試みます: username=%s", username)
        self.input(self.USERNAME, username)
        self.input(self.PASSWORD, password)
        self.click(self.LOGIN_BTN)
        logger.debug("ログインボタンをクリックしました。MFA等の追加確認が出る場合がある")
