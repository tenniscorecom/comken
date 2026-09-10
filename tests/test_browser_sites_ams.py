"""ams サイト雛形の LoginPage / ChangePasswordPage のテスト。

パスワード期限切れで変更画面へ飛ばされたときの分岐だけを確かめる
（実際の Edge は起動せず、tests/test_browser.py と同じ方針で WebDriver をモックする）。
"""

from unittest.mock import MagicMock

import pytest
from selenium.common.exceptions import NoSuchElementException

from comken.exceptions import PasswordRejectedError
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


class TestChangePasswordPageSubmission:
    """submit_new_password() — サイト側の拒否を PasswordRejectedError として伝える。"""

    def _make_change_password_page(self, tmp_path) -> ChangePasswordPage:
        session = BrowserSession(
            name="test",
            options=BrowserOptions(),
            download_dir=DownloadDir(path=tmp_path / "dl"),
            profile_dir=None,
        )
        session._driver = MagicMock()
        session._site = AMS()
        page = ChangePasswordPage(session)
        page._wait = MagicMock()  # click/input/read_text の要素待機を素通りさせる
        return page

    def test_returns_secure_page_when_site_accepts(self, tmp_path):
        """エラー表示が無ければ、通常どおり SecurePage を返す。"""
        page = self._make_change_password_page(tmp_path)
        page.session._driver.find_element.side_effect = NoSuchElementException()

        result = page.submit_new_password("New-Pass1!")

        assert isinstance(result, SecurePage)

    def test_raises_password_rejected_when_site_shows_error(self, tmp_path):
        """エラー表示があれば PasswordRejectedError（サイト側の文言つき）を送出する。"""
        page = self._make_change_password_page(tmp_path)
        page.session._driver.find_element.return_value = MagicMock()  # エラー要素あり
        page._wait.until.return_value.text = "パスワードには記号を含めてください"

        with pytest.raises(PasswordRejectedError, match="記号"):
            page.submit_new_password("weak")
