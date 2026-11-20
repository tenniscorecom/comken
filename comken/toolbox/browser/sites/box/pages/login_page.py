"""comken/toolbox/browser/sites/box/pages/login_page.py — Box のログイン画面。

Box のログインは「メールアドレス → 次へ → パスワード → ログイン」の2段階の
ことがある。1画面に両方出る場合（会社アカウントの設定など）もあるため、
どちらの形でも同じコードで動くようにしている。

パスワードはログに出さない（``Page.input()`` は値そのものを残さない）。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from comken.exceptions import LoginFailedError
from comken.toolbox.browser import Locator
from comken.toolbox.browser.sites.box.pages.app_page import AppPage

if TYPE_CHECKING:
    from comken.toolbox.browser.page.waiting import Condition

logger = logging.getLogger(__name__)


class LoginPage(AppPage):
    """Box のログイン画面（/login）。"""

    PATH = "/login"

    # ── セレクター ──
    # メールアドレスの入力欄
    # 根拠: https://github.com/veerDS/automation_test_jenkins の
    # src/main/java/com/utils/Constants.java にある
    # ``BOX_APP_URL = "https://account.box.com/login"`` と、
    # 同じリポジトリの BoxAppLoginPage.java の ``By.id("login-email")``。
    # 独立した 2 つの Selenium 事例
    # （veerDS/automation_test_jenkins と bhandigare/UIAutomation）が
    # 同じ id を使っている。id は表示文字列ではないので UI の言語に依存しない。
    EMAIL_INPUT = Locator.id("login-email")

    # 「次へ」ボタン（メールアドレス入力画面）
    # 根拠: 上記 2 つの Selenium 事例の ``By.id("login-submit")``。
    NEXT_BTN = Locator.id("login-submit")

    # パスワードの入力欄
    # 根拠: 上記 2 つの Selenium 事例の ``By.id("password-login")``。
    PASSWORD_INPUT = Locator.id("password-login")

    # 「ログイン」ボタン（パスワード入力画面）
    # 根拠: 上記 2 つの Selenium 事例の ``By.id("login-submit-password")``。
    LOGIN_BTN = Locator.id("login-submit-password")

    # ログイン失敗時のエラー表示
    # 根拠: 未確認: 推測。公開資料ではこの表示要素のセレクターが見つかって
    # いない（「incorrect password」等の表示そのものは Box に存在する）。
    # 候補を複数置いて、どれか1つでも出ればエラーとして扱う。
    ERROR_MSG = Locator.css(".login-error, [data-resin-target='error-message'], form .error")

    def login(self, username: str, password: str) -> None:
        """メールアドレスとパスワードでログインする。

        Box のログインは 2 段構成のことがある（メールアドレスを入れて「次へ」→
        パスワードを入れて「ログイン」）。1画面に両方出る場合は、パスワード欄が
        既にあるので「次へ」を押さずにそのまま進む。

        ログイン後は画面が別物に差し替わる（または二段階認証の画面になる）ので、
        「URL が変わる・エラー表示が出る・パスワード欄が消える」のどれかが先に
        起きるまで待つ。**パスワードはログに出さない。**

        Args:
            username: メールアドレス。
            password: パスワード。

        Raises:
            LoginFailedError: ログイン画面にエラー表示が出た場合
                （サイト側のメッセージつき）。
        """
        self.input(self.EMAIL_INPUT, username)

        # 2 段構成のときだけ「次へ」を押す。1画面構成ならパスワード欄が既にある
        if not self.has_element(self.PASSWORD_INPUT):
            self.click(self.NEXT_BTN)
            self.wait_visible(self.PASSWORD_INPUT)

        self.input(self.PASSWORD_INPUT, password)

        url_before_login = self.session.current_url
        self.click(self.LOGIN_BTN)
        logger.info(
            "Boxへログインを送信しました。二段階認証が要求される場合は表示中のEdgeで承認してください"
        )

        # ログイン結果のどれかが先に起きるまで待つ。二段階認証へ進む場合は
        # URL が変わらないことがあるので、パスワード欄の消滅も判定に含める
        self.wait_until_any(
            self.url_changed(url_before_login),
            self.text_shown(self.ERROR_MSG),
            self.login_form_gone(),
        )
        self.raise_if_shown(self.ERROR_MSG, LoginFailedError)

    def login_form_gone(self) -> Condition:
        """ログインフォーム（パスワード欄）が無くなることを表す条件。

        ログイン後は画面が別物に差し替わるため、パスワード欄が消えるのを
        「ログイン手続きが進んだ」判定に使う。二段階認証の画面へ移った場合も
        パスワード欄は消える。
        """
        return lambda driver: not driver.find_elements(*self.PASSWORD_INPUT)

    def error_message(self) -> str:
        """ログイン画面のエラー表示を返す。エラーが出ていなければ空文字。"""
        if not self.has_element(self.ERROR_MSG):
            return ""
        return self.read_text(self.ERROR_MSG)
