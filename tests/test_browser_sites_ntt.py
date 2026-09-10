"""NTT西・NTT東の共有サイト実装のテスト。

実際の Edge は起動せず、WebDriver をモックに差し替えて配線だけを確認する
（tests/test_browser.py と同じ方針）。ここで確かめたいのは、
「pages/ を共有していても各サイトの BASE_URL が混ざらないこと」。
"""

from unittest.mock import MagicMock

import pytest
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait

from comken.exceptions import LoginFailedError
from comken.toolbox.browser import BrowserOptions, DownloadDir
from comken.toolbox.browser.management.sessions import BrowserSession
from comken.toolbox.browser.sites import SITES, NTTEast, NTTWest
from comken.toolbox.browser.sites.ntt.pages.login_page import LoginPage
from comken.toolbox.browser.sites.ntt.pages.secure_page import SecurePage


def _make_session(tmp_path, site, name: str = "test") -> BrowserSession:
    """Edge を起動せずに、site に紐づいた起動済みセッションを作る。"""
    session = BrowserSession(
        name=name,
        options=BrowserOptions(),
        download_dir=DownloadDir(path=tmp_path / f"dl_{name}"),
        profile_dir=None,
    )
    session._driver = MagicMock()
    session._site = site
    return session


class TestPublicApi:
    """雛形（sample）と同じ扱いで公開する。"""

    def test_exports_ntt_sites_without_registering_as_library_sites(self):
        """URL がダミーのままなので、SITES（公認一覧）には登録しない。"""
        for site in (NTTWest, NTTEast):
            assert site.NAME
            assert site.BASE_URL
            assert site.OWNER
            assert site not in SITES

    def test_west_and_east_have_distinct_name_and_url(self):
        """NAME・BASE_URL は姉妹サイトでも別々。"""
        assert NTTWest.NAME != NTTEast.NAME
        assert NTTWest.BASE_URL != NTTEast.BASE_URL


class TestSharedPagesResolvePerSiteBaseUrl:
    """pages/ を共有していても、実際に開く URL は起動したサイトのものになる。"""

    def test_login_page_opens_west_url(self, tmp_path):
        session = _make_session(tmp_path, NTTWest())
        page = LoginPage(session)

        page.go("/login")

        page.session._driver.get.assert_called_once_with(f"{NTTWest.BASE_URL}/login")

    def test_login_page_opens_east_url(self, tmp_path):
        session = _make_session(tmp_path, NTTEast())
        page = LoginPage(session)

        page.go("/login")

        page.session._driver.get.assert_called_once_with(f"{NTTEast.BASE_URL}/login")


def _make_login_page(tmp_path, current_url_after_login: str) -> LoginPage:
    """ログインボタンを押した後の current_url を差し替えた LoginPage を作る。"""
    session = _make_session(tmp_path, NTTWest())
    session._driver.current_url = current_url_after_login
    # has_element() の既定は「要素なし」。ログインエラー表示ありのテストだけ
    # 個別に find_element.side_effect を外して上書きする
    session._driver.find_element.side_effect = NoSuchElementException()
    page = LoginPage(session)
    page._wait = MagicMock()  # click/input の要素待機を素通りさせる
    return page


class TestLoginFailure:
    """login() — 単純な認証情報間違いを LoginFailedError として伝える。"""

    def test_raises_login_failed_when_error_shown(self, tmp_path):
        """URL は変わらずエラー表示が出ていれば LoginFailedError（サイト側の文言つき）。"""
        page = _make_login_page(tmp_path, current_url_after_login=f"{NTTWest.BASE_URL}/login")
        page.session._driver.find_element.side_effect = None
        page.session._driver.find_element.return_value = MagicMock()  # エラー要素あり
        page._wait.until.return_value.text = "ユーザー名またはパスワードが違います"

        with pytest.raises(LoginFailedError, match="ユーザー名またはパスワードが違います"):
            page.login("user01", "wrong-password")

    def test_returns_secure_page_when_no_error_shown(self, tmp_path):
        """エラー表示が無ければ従来どおり SecurePage（has_element の既定値）。"""
        page = _make_login_page(tmp_path, current_url_after_login=f"{NTTWest.BASE_URL}/home")

        result = page.login("user01", "password")

        assert isinstance(result, SecurePage)

    def test_catches_error_message_that_appears_after_a_short_async_delay(self, tmp_path):
        """エラー表示が非同期で少し遅れて出るサイトでも、クリック直後の一度きりの
        確認では見逃さず、URLが変わるかエラーが出るまで待ってから正しく検知する
        （レースコンディションの回帰確認。このテストだけ _wait を完全モックにせず、
        短いポーリング間隔の実物に差し替えて実際の待機ロジックを検証する）。
        """
        page = _make_login_page(tmp_path, current_url_after_login=f"{NTTWest.BASE_URL}/login")
        page._wait = WebDriverWait(page.session.raw, timeout=1, poll_frequency=0.05)

        # ERROR_MESSAGE だけ最初の数回は見つからない（＝非同期で少し遅れて出る）
        # ことにする。USERNAME/PASSWORD/LOGIN_BTN は通常どおり即座に見つかる
        error_lookup_count = 0

        def find_element_side_effect(by, value):
            nonlocal error_lookup_count
            element = MagicMock()
            element.is_displayed.return_value = True
            if (by, value) != tuple(LoginPage.ERROR_MESSAGE):
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
        page = _make_login_page(tmp_path, current_url_after_login=f"{NTTWest.BASE_URL}/home")
        page.click = MagicMock()

        result = page.login("user01", "password")

        page.click.assert_not_called()
        assert isinstance(result, SecurePage)

    def test_clicks_login_button_when_present(self, tmp_path):
        """ボタンが見つかれば、従来どおりクリックしてから画面判定へ進む。"""
        page = _make_login_page(tmp_path, current_url_after_login=f"{NTTWest.BASE_URL}/home")
        page.click = MagicMock()

        def find_element_side_effect(by, value):
            if (by, value) == tuple(page.LOGIN_BTN):
                return MagicMock()
            raise NoSuchElementException()

        page.session._driver.find_element.side_effect = find_element_side_effect

        result = page.login("user01", "password")

        page.click.assert_called_once_with(page.LOGIN_BTN)
        assert isinstance(result, SecurePage)
