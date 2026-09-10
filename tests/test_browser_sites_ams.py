"""ams サイト雛形の LoginPage / ChangePasswordPage のテスト。

パスワード期限切れで変更画面へ飛ばされたときの分岐だけを確かめる
（実際の Edge は起動せず、tests/test_browser.py と同じ方針で WebDriver をモックする）。
"""

from unittest.mock import MagicMock

from comken.toolbox.browser import BrowserOptions, DownloadDir
from comken.toolbox.browser.management.sessions import BrowserSession
from comken.toolbox.browser.sites.ams.pages.change_password_page import ChangePasswordPage
from comken.toolbox.browser.sites.ams.pages.login_page import LoginPage
from comken.toolbox.browser.sites.ams.pages.secure_page import SecurePage
from comken.toolbox.browser.sites.ams.site import AMS


def _make_login_page(tmp_path, current_url_after_login: str) -> LoginPage:
    """ログインボタンを押した後の current_url を差し替えた LoginPage を作る。"""
    session = BrowserSession(
        name="test",
        options=BrowserOptions(),
        download_dir=DownloadDir(path=tmp_path / "dl"),
        profile_dir=None,
    )
    session._driver = MagicMock()
    session._driver.current_url = current_url_after_login
    session._site = AMS()
    page = LoginPage(session)
    page._wait = MagicMock()  # click/input の要素待機を素通りさせる
    return page


class TestLoginPasswordExpiry:
    """current_url によるパスワード期限切れの検知。"""

    def test_returns_secure_page_when_not_redirected(self, tmp_path):
        """URL が変わらなければ通常どおり SecurePage。"""
        page = _make_login_page(tmp_path, current_url_after_login=f"{AMS.BASE_URL}/home")

        result = page.login("user01", "password")

        assert isinstance(result, SecurePage)

    def test_returns_change_password_page_when_redirected(self, tmp_path):
        """変更画面の PATH を含む URL に飛ばされたら ChangePasswordPage。"""
        redirected_url = f"{AMS.BASE_URL}{ChangePasswordPage.PATH}"
        page = _make_login_page(tmp_path, current_url_after_login=redirected_url)

        result = page.login("user01", "password")

        assert isinstance(result, ChangePasswordPage)


class TestCredentialFieldConstant:
    """save_credential() へ渡す site/field をリテラルで書き直させないための配線。"""

    def test_credential_field_is_a_constant_not_a_literal(self, tmp_path):
        """呼び出し側は ChangePasswordPage.CREDENTIAL_FIELD と session.name を
        参照する設計（docs/credentials.md・docs/browser.md の例と同じ）。
        リテラルで typo しても気づけない事故を防ぐため、値そのものではなく
        「参照できること」を確認する。
        """
        redirected_url = f"{AMS.BASE_URL}{ChangePasswordPage.PATH}"
        page = _make_login_page(tmp_path, current_url_after_login=redirected_url)

        result = page.login("user01", "password")

        assert isinstance(result, ChangePasswordPage)
        assert result.session.name == page.session.name
        assert ChangePasswordPage.CREDENTIAL_FIELD == "password"
