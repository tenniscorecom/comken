"""comken/toolbox/browser/sites/ams/pages/change_password_page.py — パスワード変更画面（雛形）

パスワードが有効期限切れのとき、ログイン後に強制的に飛ばされる画面。
URL や要素セレクタは example の値のまま。利用プロジェクト側で継承して書き換える。
"""

# TYPE_CHECKING 内の SecurePage を型注釈で使うため、注釈の評価を遅延する。
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from comken.exceptions import PasswordRejectedError
from comken.toolbox.browser import Locator
from comken.toolbox.browser.sites.ams.pages.app_page import AppPage

if TYPE_CHECKING:
    from comken.toolbox.browser.sites.ams.pages.secure_page import SecurePage

logger = logging.getLogger(__name__)


class ChangePasswordPage(AppPage):
    """パスワード期限切れ時の変更画面（雛形）。"""

    # LoginPage.login() が current_url にこの文字列が含まれるかで遷移を検知する。
    PATH = "/change-password"
    NEW_PASSWORD = Locator.id("newPassword")
    CONFIRM_PASSWORD = Locator.id("confirmPassword")
    SUBMIT_BTN = Locator.css("button[type=submit]")
    # サイト側が新しいパスワードを拒否した（記号が足りない等）ときだけ現れる目印。
    # 実際のセレクタ・拒否の見分け方はサイトごとに違うので、利用プロジェクト側で
    # 実物のHTMLに合わせて書き換える。
    ERROR_MESSAGE = Locator.css(".password-error")

    def submit_new_password(self, new_password: str) -> SecurePage:
        """新しいパスワードを2回入力して送信し、SecurePage を返す。

        呼び出し側で用意した新しいパスワードをそのまま渡す。
        「どこでパスワードを決めるか」（CLIで受け付ける等）はこの画面の
        責務ではない（comken.toolbox.credentials.prompt_new_password() /
        change_password()）。

        サイト側が拒否した場合（記号が足りない・文字数が足りない等）は
        ``PasswordRejectedError`` を送出する。``change_password()`` はこれを
        受け取って自動で聞き直す（利用プロジェクト側で再試行ループを
        書かなくてよい）。
        拒否の表示は非同期（Ajax 等）で少し遅れて出るサイトもあるため、送信
        直後に一度だけ確認するのではなく、「URL が変わる」か「拒否の表示が
        出る」のどちらかが起きるまで待ってから判定する。
        """
        from comken.toolbox.browser.sites.ams.pages.secure_page import SecurePage

        url_before_submit = self.session.current_url

        self.input(self.NEW_PASSWORD, new_password)
        self.input(self.CONFIRM_PASSWORD, new_password)
        self.click(self.SUBMIT_BTN)

        self.wait_for_result(url_before_submit, self.ERROR_MESSAGE)

        current_url = self.session.current_url
        # 想定外の画面へ飛んだ場合に切り分けられるよう info で残す
        # （既定のログレベルは INFO。DEBUG だと通常実行では残らない）
        logger.info("パスワード変更の送信結果を判定します: current_url=%s", current_url)

        self.raise_if_shown(self.ERROR_MESSAGE, PasswordRejectedError)
        return self.to(SecurePage)
