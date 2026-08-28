"""NTT西・NTT東の共有サイト実装のテスト。

実際の Edge は起動せず、WebDriver をモックに差し替えて配線だけを確認する
（tests/test_browser.py と同じ方針）。ここで確かめたいのは、
「pages/ を共有していても各サイトの BASE_URL が混ざらないこと」。
"""

from unittest.mock import MagicMock

from comken.toolbox.browser import BrowserOptions, DownloadDir
from comken.toolbox.browser.management.sessions import BrowserSession
from comken.toolbox.browser.sites import SITES, NTTHigashi, NTTNishi
from comken.toolbox.browser.sites.ntt.pages.login_page import LoginPage


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
        for site in (NTTNishi, NTTHigashi):
            assert site.NAME
            assert site.BASE_URL
            assert site.OWNER
            assert site not in SITES

    def test_nishi_and_higashi_have_distinct_name_and_url(self):
        """NAME・BASE_URL は姉妹サイトでも別々。"""
        assert NTTNishi.NAME != NTTHigashi.NAME
        assert NTTNishi.BASE_URL != NTTHigashi.BASE_URL


class TestSharedPagesResolvePerSiteBaseUrl:
    """pages/ を共有していても、実際に開く URL は起動したサイトのものになる。"""

    def test_login_page_opens_nishi_url(self, tmp_path):
        session = _make_session(tmp_path, NTTNishi())
        page = LoginPage(session)

        page.go("/login")

        page.session._driver.get.assert_called_once_with(f"{NTTNishi.BASE_URL}/login")

    def test_login_page_opens_higashi_url(self, tmp_path):
        session = _make_session(tmp_path, NTTHigashi())
        page = LoginPage(session)

        page.go("/login")

        page.session._driver.get.assert_called_once_with(f"{NTTHigashi.BASE_URL}/login")
