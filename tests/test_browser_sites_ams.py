"""ams サイト雛形の LoginPage / ChangePasswordPage のテスト。

パスワード期限切れで変更画面へ飛ばされたときの分岐だけを確かめる
（実際の Edge は起動せず、tests/test_browser.py と同じ方針で WebDriver をモックする）。
"""

from unittest.mock import MagicMock

import pytest
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait

from comken.exceptions import LoginFailedError, PasswordRejectedError
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
    # has_element() の既定は「要素なし」。ログインエラー表示ありのテストだけ
    # 個別に find_element.side_effect を外して上書きする
    session._driver.find_element.side_effect = NoSuchElementException()
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


class TestLoginFailure:
    """login() — 単純な認証情報間違い（期限切れとは別）を LoginFailedError として伝える。"""

    def test_raises_login_failed_when_error_shown(self, tmp_path):
        """URL は変わらずエラー表示が出ていれば LoginFailedError（サイト側の文言つき）。"""
        page = _make_login_page(tmp_path, current_url_after_login=f"{AMS.BASE_URL}/login")
        page.session._driver.find_element.side_effect = None
        page.session._driver.find_element.return_value = MagicMock()  # エラー要素あり
        page._wait.until.return_value.text = "ユーザー名またはパスワードが違います"

        with pytest.raises(LoginFailedError, match="ユーザー名またはパスワードが違います"):
            page.login("user01", "wrong-password")

    def test_returns_secure_page_when_no_error_shown(self, tmp_path):
        """エラー表示が無ければ従来どおり SecurePage（回帰確認、has_element の既定値）。"""
        page = _make_login_page(tmp_path, current_url_after_login=f"{AMS.BASE_URL}/home")

        result = page.login("user01", "password")

        assert isinstance(result, SecurePage)

    def test_catches_error_message_that_appears_after_a_short_async_delay(self, tmp_path):
        """エラー表示が非同期で少し遅れて出るサイトでも、クリック直後の一度きりの
        確認では見逃さず、URLが変わるかエラーが出るまで待ってから正しく検知する
        （レースコンディションの回帰確認。このテストだけ _wait を完全モックにせず、
        短いポーリング間隔の実物に差し替えて実際の待機ロジックを検証する）。
        """
        page = _make_login_page(tmp_path, current_url_after_login=f"{AMS.BASE_URL}/login")
        page._wait = WebDriverWait(page.session.raw, timeout=1, poll_frequency=0.05)

        # ERROR_MSG だけ最初の数回は見つからない（＝非同期で少し遅れて出る）
        # ことにする。USERNAME/PASSWORD/LOGIN_BTN は通常どおり即座に見つかる
        error_lookup_count = 0

        def find_element_side_effect(by, value):
            nonlocal error_lookup_count
            element = MagicMock()
            element.is_displayed.return_value = True
            if (by, value) != tuple(LoginPage.ERROR_MSG):
                return element
            error_lookup_count += 1
            if error_lookup_count < 3:
                raise NoSuchElementException()
            element.text = "非同期で少し遅れて出たエラー"
            return element

        page.session._driver.find_element.side_effect = find_element_side_effect

        with pytest.raises(LoginFailedError, match="非同期で少し遅れて出たエラー"):
            page.login("user01", "wrong-password")


class TestLoginButtonSkip:
    """ログインボタンが既に消えている場合（非同期で先にログインが進んだ場合）の扱い。"""

    def test_skips_click_when_login_button_not_found(self, tmp_path):
        """ボタンが見つからなければクリックを省略し、そのまま画面判定へ進む。"""
        page = _make_login_page(tmp_path, current_url_after_login=f"{AMS.BASE_URL}/home")
        page.click = MagicMock()

        result = page.login("user01", "password")

        page.click.assert_not_called()
        assert isinstance(result, SecurePage)

    def test_clicks_login_button_when_present(self, tmp_path):
        """ボタンが見つかれば、従来どおりクリックしてから画面判定へ進む。"""
        page = _make_login_page(tmp_path, current_url_after_login=f"{AMS.BASE_URL}/home")
        page.click = MagicMock()

        def find_element_side_effect(by, value):
            if (by, value) == tuple(page.LOGIN_BTN):
                return MagicMock()
            raise NoSuchElementException()

        page.session._driver.find_element.side_effect = find_element_side_effect

        result = page.login("user01", "password")

        page.click.assert_called_once_with(page.LOGIN_BTN)
        assert isinstance(result, SecurePage)


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

    def test_catches_rejection_message_that_appears_after_a_short_async_delay(self, tmp_path):
        """拒否表示が非同期で少し遅れて出るサイトでも、送信直後の一度きりの
        確認では見逃さず、URLが変わるか拒否表示が出るまで待ってから正しく
        検知する（レースコンディションの回帰確認。このテストだけ _wait を
        完全モックにせず、短いポーリング間隔の実物に差し替えて実際の
        待機ロジックを検証する）。
        """
        page = self._make_change_password_page(tmp_path)
        page.session._driver.current_url = f"{AMS.BASE_URL}{ChangePasswordPage.PATH}"
        page._wait = WebDriverWait(page.session.raw, timeout=1, poll_frequency=0.05)

        # ERROR_MESSAGE だけ最初の数回は見つからない（＝非同期で少し遅れて出る）
        # ことにする。NEW_PASSWORD/CONFIRM_PASSWORD/SUBMIT_BTN は通常どおり即座に見つかる
        error_lookup_count = 0

        def find_element_side_effect(by, value):
            nonlocal error_lookup_count
            element = MagicMock()
            element.is_displayed.return_value = True
            if (by, value) != tuple(ChangePasswordPage.ERROR_MESSAGE):
                return element
            error_lookup_count += 1
            if error_lookup_count < 3:
                raise NoSuchElementException()
            element.text = "非同期で少し遅れて出た拒否メッセージ"
            return element

        page.session._driver.find_element.side_effect = find_element_side_effect

        with pytest.raises(PasswordRejectedError, match="非同期で少し遅れて出た拒否メッセージ"):
            page.submit_new_password("New-Pass1!")
