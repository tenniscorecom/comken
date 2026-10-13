"""cms サイト雛形のテスト。

雛形サイトなので、

- ``SITES`` に自動登録される（``NAME`` の衝突なし）
- ``CMS.BASE_URL`` / ``OWNER`` / ``OPTIONS`` が雛形の値になっている
- ``go_login()`` がログイン画面クラスへ遷移を組み立てられる
- 単純な認証情報間違いが ``LoginFailedError`` として伝わる
- パスワード期限切れ対応は雛形では未提供（TODO コメントで案内）

の最低限を確かめる（実際の Edge は起動せず、tests/test_browser.py と同じ方針で
WebDriver をモックする）。
"""

from unittest.mock import MagicMock

import pytest
from selenium.common.exceptions import NoSuchElementException

from comken.exceptions import LoginFailedError
from comken.toolbox.browser import BrowserOptions, DownloadDir
from comken.toolbox.browser.management.sessions import BrowserSession
from comken.toolbox.browser.sites import SITES
from comken.toolbox.browser.sites.cms import CMS, CMSBrowserOptions
from comken.toolbox.browser.sites.cms.pages.login_page import LoginPage
from comken.toolbox.browser.sites.cms.pages.top_page import TopPage
from comken.toolbox.browser.sites.cms.site import CMS as CMSFromSite


class TestSITESAutoRegistration:
    """``CMS`` は ``NAME`` を上書きしているので SITES（公認一覧）に登録される。"""

    def test_cms_is_registered_in_sites(self):
        assert CMS in SITES

    def test_cms_reexported_from_site_module_matches(self):
        """``sites.cms.__init__`` の ``CMS`` と ``sites.cms.site`` の ``CMS`` が一致する
        （雛形の見本 ``ouju`` / ``ams`` と同じ公開方法）"""
        assert CMS is CMSFromSite

    def test_cms_options_class_is_exported(self):
        """``CMSBrowserOptions`` がパッケージレベルで取り出せる。"""
        assert CMS.OPTIONS is CMSBrowserOptions
        assert issubclass(CMSBrowserOptions, BrowserOptions)

    def test_all_sites_have_unique_names(self):
        """``_check_not_in_library()`` の衝突検出が正しく動くよう、NAME はサイト間で重複しない。"""
        names = [site.NAME for site in SITES]
        assert len(names) == len(set(names))


class TestCMSMetadata:
    """雛形の値（``NAME`` / ``BASE_URL`` / ``OWNER`` / ``OPTIONS``）の確認。"""

    def test_name_and_owner(self):
        assert CMS.NAME == "cms"
        assert CMS.OWNER == "comken"

    def test_base_url_is_rfc2606_example(self):
        """``BASE_URL`` は RFC 2606 の example ドメイン（実在しない）。"""
        assert CMS.BASE_URL == "https://cms.example.com"

    def test_options_default_does_not_override_browser_options(self):
        """雛形では ``CMSBrowserOptions`` は既定から意図的に変えない（書き換え欄だけ残す形）。"""
        defaults = BrowserOptions()
        options = CMSBrowserOptions()
        assert options.DRIVER_PATH == defaults.DRIVER_PATH
        assert options.WINDOW_SIZE == defaults.WINDOW_SIZE


class TestGoLogin:
    """``CMS.go_login()`` がログイン画面クラスへ遷移を組み立てられる。"""

    def test_go_login_opens_login_page(self, tmp_path):
        session = BrowserSession(
            name="test",
            options=BrowserOptions(),
            download_dir=DownloadDir(path=tmp_path / "dl"),
            profile_dir=None,
        )
        session._driver = MagicMock()
        site = CMS()
        # SiteBase.to() は self.session を見るので、site 側に session を結ぶ。
        # Page._base_url のフォールバックは self.session._site を見るので、
        # BASE_URL 解決のため session._site にも site を結ぶ（__enter__ と同じ形）。
        site.session = session
        session._site = site

        page = site.go_login()

        assert isinstance(page, LoginPage)
        page.session._driver.get.assert_called_once_with(f"{CMS.BASE_URL}/login")

    def test_go_top_opens_top_page(self, tmp_path):
        """``CMS.go_top()`` はログイン後のトップ画面を /top で開く。"""
        session = BrowserSession(
            name="test",
            options=BrowserOptions(),
            download_dir=DownloadDir(path=tmp_path / "dl"),
            profile_dir=None,
        )
        session._driver = MagicMock()
        site = CMS()
        # SiteBase.to() は self.session を見るので、site 側に session を結ぶ。
        # Page._base_url のフォールバックは self.session._site を見るので、
        # BASE_URL 解決のため session._site にも site を結ぶ（__enter__ と同じ形）。
        site.session = session
        session._site = site

        page = site.go_top()

        assert isinstance(page, TopPage)
        page.session._driver.get.assert_called_once_with(f"{CMS.BASE_URL}/top")


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
    session._site = CMS()
    page = LoginPage(session)
    page._wait = MagicMock()  # click/input の要素待機を素通りさせる
    return page


class TestLoginFailure:
    """login() — 単純な認証情報間違いを LoginFailedError として伝える。"""

    def test_raises_login_failed_when_error_shown(self, tmp_path):
        """URL は変わらずエラー表示が出ていれば LoginFailedError（サイト側の文言つき）。"""
        page = _make_login_page(tmp_path, current_url_after_login=f"{CMS.BASE_URL}/login")
        page.session._driver.find_element.side_effect = None
        page.session._driver.find_element.return_value = MagicMock()  # エラー要素あり
        page._wait.until.return_value.text = "ユーザー名またはパスワードが違います"

        with pytest.raises(LoginFailedError, match="ユーザー名またはパスワードが違います"):
            page.login("user01", "wrong-password")

    def test_returns_top_page_when_no_error_shown(self, tmp_path):
        """エラー表示が無ければ TopPage を返す（has_element の既定値）。"""
        page = _make_login_page(tmp_path, current_url_after_login=f"{CMS.BASE_URL}/top")

        result = page.login("user01", "password")

        assert isinstance(result, TopPage)


# 非同期で少し遅れて出るエラー表示のレースコンディション回帰テストは
# tests/test_browser.py の TestPage.test_wait_for_result_* に集約してある
# （wait_for_result() 自体の待機ロジックなので、サイトごとに複製しない）。
