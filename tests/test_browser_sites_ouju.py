"""ouju サイト雛形の LoginPage のテスト。

単純な認証情報間違いによる LoginFailedError の検知だけを確かめる
（実際の Edge は起動せず、tests/test_browser.py と同じ方針で WebDriver をモックする）。
"""

from unittest.mock import MagicMock

import pytest
from selenium.common.exceptions import NoSuchElementException

from comken.exceptions import LoginFailedError
from comken.toolbox.browser import BrowserOptions, DownloadDir
from comken.toolbox.browser.management.sessions import BrowserSession
from comken.toolbox.browser.sites.ouju.pages.login_page import LoginPage
from comken.toolbox.browser.sites.ouju.pages.secure_page import SecurePage
from comken.toolbox.browser.sites.ouju.site import Ouju


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
    session._site = Ouju()
    page = LoginPage(session)
    page._wait = MagicMock()  # click/input の要素待機を素通りさせる
    return page


class TestLoginFailure:
    """login() — 単純な認証情報間違いを LoginFailedError として伝える。"""

    def test_raises_login_failed_when_error_shown(self, tmp_path):
        """URL は変わらずエラー表示が出ていれば LoginFailedError（サイト側の文言つき）。"""
        page = _make_login_page(tmp_path, current_url_after_login=f"{Ouju.BASE_URL}/login")
        page.session._driver.find_element.side_effect = None
        page.session._driver.find_element.return_value = MagicMock()  # エラー要素あり
        page._wait.until.return_value.text = "ユーザー名またはパスワードが違います"

        with pytest.raises(LoginFailedError, match="ユーザー名またはパスワードが違います"):
            page.login("user01", "wrong-password")

    def test_returns_secure_page_when_no_error_shown(self, tmp_path):
        """エラー表示が無ければ従来どおり SecurePage（has_element の既定値）。"""
        page = _make_login_page(tmp_path, current_url_after_login=f"{Ouju.BASE_URL}/home")

        result = page.login("user01", "password")

        assert isinstance(result, SecurePage)


# 非同期で少し遅れて出るエラー表示のレースコンディション回帰テストは
# tests/test_browser.py の TestPage.test_wait_for_result_* に集約してある
# （wait_for_result() 自体の待機ロジックなので、サイトごとに複製しない）。


class TestLoginButtonSkip:
    """ログインボタンが既に消えている場合（非同期で先にログインが進んだ場合）の扱い。"""

    def test_skips_click_when_login_button_not_found(self, tmp_path):
        """ボタンが見つからなければクリックを省略し、そのまま画面判定へ進む。"""
        page = _make_login_page(tmp_path, current_url_after_login=f"{Ouju.BASE_URL}/home")
        page.click = MagicMock()

        result = page.login("user01", "password")

        page.click.assert_not_called()
        assert isinstance(result, SecurePage)

    def test_clicks_login_button_when_present(self, tmp_path):
        """ボタンが見つかれば、従来どおりクリックしてから画面判定へ進む。"""
        page = _make_login_page(tmp_path, current_url_after_login=f"{Ouju.BASE_URL}/home")
        page.click = MagicMock()

        def find_element_side_effect(by, value):
            if (by, value) == tuple(page.LOGIN_BTN):
                return MagicMock()
            raise NoSuchElementException()

        page.session._driver.find_element.side_effect = find_element_side_effect

        result = page.login("user01", "password")

        page.click.assert_called_once_with(page.LOGIN_BTN)
        assert isinstance(result, SecurePage)
