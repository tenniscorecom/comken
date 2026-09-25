"""NTT西・NTT東の共有サイト実装のテスト。

実際の Edge は起動せず、WebDriver をモックに差し替えて配線だけを確認する
（tests/test_browser.py と同じ方針）。ここで確かめたいのは、
「pages/ を共有していても各サイトの BASE_URL が混ざらないこと」。
"""

from unittest.mock import MagicMock

from comken.toolbox.browser import BrowserOptions, DownloadDir
from comken.toolbox.browser.management.sessions import BrowserSession
from comken.toolbox.browser.sites import SITES, NTTEast, NTTWest
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
    """NTT西・NTT東 は SITE 配下の公開名前空間に出す。"""

    def test_exports_ntt_sites_as_library_sites(self):
        """`NAME` と `BASE_URL` を上書きしているので、SITES（公認一覧）に登録される。"""
        for site in (NTTWest, NTTEast):
            assert site.NAME
            assert site.BASE_URL
            assert site.OWNER
            assert site in SITES

    def test_west_and_east_have_distinct_name_and_url(self):
        """NAME・BASE_URL は姉妹サイトでも別々。"""
        assert NTTWest.NAME != NTTEast.NAME
        assert NTTWest.BASE_URL != NTTEast.BASE_URL


class TestSITESAutoRegistration:
    """``browser/sites/__init__.py`` の SITES は ``find_subclasses`` で自動収集される。
    NTTWest / NTTEast も ``NAME`` を上書きしているので SITES に入る。
    """

    def test_ntt_sites_in_sites_tuple(self):
        """NTTWest / NTTEast は SITES に含まれる（順序はモジュール名の昇順で east → west）。"""
        assert NTTEast in SITES
        assert NTTWest in SITES
        ntt_modules = [c.__module__ for c in SITES if c.__name__ in ("NTTEast", "NTTWest")]
        assert ntt_modules == [
            "comken.toolbox.browser.sites.ntt.east",
            "comken.toolbox.browser.sites.ntt.west",
        ]

    def test_base_ntt_site_is_excluded_by_empty_name(self):
        """``NTTSiteBase`` は ``NAME`` を空のままにしているので SITES に入らない。"""
        from comken.toolbox.browser.sites.ntt.base import NTTSiteBase

        assert NTTSiteBase not in SITES
        assert all(s.NAME for s in SITES)

    def test_salesforce_report_browser_base_is_not_a_library_site(self):
        """``SalesforceReportBrowser`` は組織クラスの土台なので、NAME を持っていても入らない。

        入ってしまうと、プロジェクト側が NAME を書かずに継承したクラスが
        この土台の NAME と衝突して、起動時に BrowserError になる。
        """
        from comken.toolbox.browser.sites.salesforce.base import SalesforceReportBrowser

        assert SalesforceReportBrowser.NAME
        assert SalesforceReportBrowser not in SITES

    def test_all_sites_have_unique_names(self):
        """``_check_not_in_library()`` の衝突検出が正しく動くよう、NAME はサイト間で重複しない。"""
        names = [site.NAME for site in SITES]
        assert len(names) == len(set(names))


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
