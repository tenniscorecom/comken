"""comken/toolbox/browser/sites/box/pages/login_page.py — Box のログイン画面。

Box のログインは ID/パスワードを入力しない。ログイン画面に出る
「サインインで続行」ボタンを押すと Microsoft（など）のアカウント選択へ進み、
あとは人が2段階認証も含めて承認する（待つのは ``Box.login()``）。

英語UIのときの文言は未確認なので、"Continue" を含むものにも当たるようにしている。
"""

from __future__ import annotations

import logging

from comken.exceptions import ElementNotFoundError
from comken.toolbox.browser import Locator
from comken.toolbox.browser.sites.box.pages.app_page import AppPage

logger = logging.getLogger(__name__)


class LoginPage(AppPage):
    """Box のログイン画面（/login）。"""

    PATH = "/login"

    # ── セレクター ──
    # 「サインインで続行」ボタン
    # 根拠: 利用者の画面の文言（日本語）。英語は 未確認: 推測
    # 英語UIのときの文言は確認できていないため、"Continue" を含むものにも
    # 当たるようにしている（属性ではなく表示文字列でしか取れないため、
    # 英語と日本語の両方に当たる書き方にした）。
    # button / role="button" / a のどれでも押せるようにしている。
    CONTINUE_BTN = Locator.xpath(
        "//button[contains(., 'サインインで続行') or contains(., 'Continue')]"
        " | //*[@role='button'][contains(., 'サインインで続行') or contains(., 'Continue')]"
        " | //a[contains(., 'サインインで続行') or contains(., 'Continue')]"
    )

    # ログイン失敗時のエラー表示
    # 根拠: 未確認: 推測。公開資料ではこの表示要素のセレクターが見つかって
    # いない（「incorrect password」等の表示そのものは Box に存在する）。
    # 候補を複数置いて、どれか1つでも出ればエラーとして扱う。
    ERROR_MSG = Locator.css(".login-error, [data-resin-target='error-message'], form .error")

    def continue_sign_in(self) -> None:
        """「サインインで続行」ボタンを押す。

        ボタンが画面に出てくるまで待って押す。押したあとは Microsoft（など）
        のアカウント選択画面へ進み、2段階認証が要るときは人が承認する
        （待つのは ``Box.wait_for_manual_login()``）。

        既にログイン済みでログイン画面が出ていない場合は、ボタンが
        見つからないので何もしない（ログイン済みかどうかは
        ``Box.wait_for_manual_login()`` が判定する）。
        """
        try:
            self.wait_visible(self.CONTINUE_BTN)
        except ElementNotFoundError:
            logger.warning(
                "「サインインで続行」ボタンが見つかりません（ログイン済みの可能性）: %s",
                self.CONTINUE_BTN,
            )
            return
        self.click(self.CONTINUE_BTN)

    def error_message(self) -> str:
        """ログイン画面のエラー表示を返す。エラーが出ていなければ空文字。"""
        if not self.has_element(self.ERROR_MSG):
            return ""
        return self.read_text(self.ERROR_MSG)
