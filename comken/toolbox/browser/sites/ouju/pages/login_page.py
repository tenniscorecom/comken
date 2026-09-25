"""comken/toolbox/browser/sites/ouju/pages/login_page.py — ログイン画面（応需システムの雛形）

URL や要素セレクタは example の値のまま。利用プロジェクト側で継承して書き換える。
"""

# TYPE_CHECKING 内の SecurePage を型注釈で使うため、注釈の評価を遅延する。
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from comken.exceptions import LoginFailedError
from comken.toolbox.browser import Locator
from comken.toolbox.browser.sites.ouju.pages.app_page import AppPage

if TYPE_CHECKING:
    # IDE の補完・型チェック用。ランタイムでは import されない
    from comken.toolbox.browser.sites.ouju.pages.secure_page import SecurePage

logger = logging.getLogger(__name__)


class LoginPage(AppPage):
    """ログイン画面（/login）。"""

    # ── セレクター（F12 で確認した値をここに書く。画面変更時はここだけ直す） ──
    PATH = "/login"
    USERNAME = Locator.id("username")
    PASSWORD = Locator.id("password")
    LOGIN_BTN = Locator.css("button[type=submit]")
    ERROR_MSG = Locator.css(".login-error")

    def login(self, username: str, password: str) -> SecurePage:
        """ログインして SecurePage を返す。

        画面遷移メソッドは遷移先のページクラスを返す。
        呼び出し側は返ってきたオブジェクトをそのまま使える:
            secure = login_page.login("user", "pass")
            print(secure.get_heading())

        ユーザー名・パスワードが間違っている場合はログイン画面にエラー表示が
        残るため、``LoginFailedError``（サイト側のエラー文言つき）を送出する。
        呼び出し側で個別に判定を書く必要はない。エラー表示は非同期（Ajax 等）
        で少し遅れて出るサイトもあるため、クリック直後に一度だけ確認するの
        ではなく、「URL が変わる」か「エラー表示が出る」のどちらかが起きる
        まで待ってから判定する（早い方が起きた時点で確定するので、成功時に
        無駄な待ちは発生しない）。

        サイトによっては、パスワード欄への入力完了などをきっかけに非同期で
        ログインが進み、ログインボタンが押せる状態のまま消えている（既に
        ログイン済み）ことがある。押せないボタンを待って ElementNotFoundError
        になるのを避けるため、``click_if_present()`` でボタンの有無を確かめて
        から押す（無ければクリックせずそのまま画面判定へ進む）。
        """
        from comken.toolbox.browser.sites.ouju.pages.secure_page import SecurePage

        url_before_login = self.session.current_url

        self.input(self.USERNAME, username)
        self.input(self.PASSWORD, password)
        # 要素が無ければ click_if_present() 自身が info ログを残す
        self.click_if_present(self.LOGIN_BTN)

        self.wait_for_result(url_before_login, self.ERROR_MSG)
        self.raise_if_shown(self.ERROR_MSG, LoginFailedError)
        return self.to(SecurePage)
