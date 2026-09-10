"""comken/toolbox/browser/sites/ntt/pages/login_page.py — ログイン画面

※ セレクターはダミー。配置するときに実際の画面（F12 で確認した値）へ書き換える。
"""

# TYPE_CHECKING 内の SecurePage を型注釈で使うため、注釈の評価を遅延する。
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from comken.exceptions import LoginFailedError
from comken.toolbox.browser import Locator
from comken.toolbox.browser.sites.ntt.pages.app_page import AppPage

if TYPE_CHECKING:
    # IDE の補完・型チェック用。ランタイムでは import されない
    from comken.toolbox.browser.sites.ntt.pages.secure_page import SecurePage

logger = logging.getLogger(__name__)


class LoginPage(AppPage):
    """ログイン画面（/login）。NTT西・NTT東で共通のセレクター・操作を仮定している。"""

    # ── セレクター（配置時に F12 で確認した実際の値へ書き換える） ──
    USERNAME = Locator.id("username")
    PASSWORD = Locator.id("password")
    LOGIN_BTN = Locator.css(".login-btn")
    # エラー表示は AppPage.ERROR_MESSAGE（NTT西・NTT東で共通の画面上部エラー）を使う

    def login(self, username: str, password: str) -> SecurePage:
        """ログインして SecurePage（ログイン後の画面）を返す。

        ユーザー名・パスワードが間違っている場合はエラー表示が残るため、
        ``LoginFailedError``（サイト側のエラー文言つき）を送出する。エラー表示は
        非同期で少し遅れて出るサイトもあるため、クリック直後に一度だけ確認する
        のではなく、「URL が変わる」か「エラー表示が出る」のどちらかが起きるまで
        待ってから判定する（早い方が起きた時点で確定するので、成功時に無駄な
        待ちは発生しない）。

        非同期でログインが先に進み、ログインボタンが既に消えていることがある
        画面にも対応するため、クリック前にボタンの有無を確かめ、無ければ
        クリックせずそのまま画面判定へ進む。
        """
        from comken.toolbox.browser.sites.ntt.pages.secure_page import SecurePage

        url_before_login = self.session.current_url

        self.input(self.USERNAME, username)
        self.input(self.PASSWORD, password)
        if not self.click_if_present(self.LOGIN_BTN):
            # 既定のログレベルは INFO（DEBUG は既定で出ない）。想定外の
            # 分岐なので、後から実行ログを見て気付けるよう info で残す
            logger.info("ログインボタンが見当たらないためクリックを省略しました")

        self.wait_for_result(url_before_login, self.ERROR_MESSAGE)

        current_url = self.session.current_url
        # 想定外の画面へ飛んだ場合に切り分けられるよう info で残す
        # （既定のログレベルは INFO。DEBUG だと通常実行では残らない）
        logger.info("ログイン後の画面を判定します: current_url=%s", current_url)

        self.raise_if_shown(self.ERROR_MESSAGE, LoginFailedError)
        return self.to(SecurePage)
