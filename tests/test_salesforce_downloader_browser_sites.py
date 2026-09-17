"""comken.services.salesforce_downloader.browser_sites のテスト。

toolbox.salesforce.sites.site_for() のブラウザ版。判定方法が同じなので、
tests/test_salesforce.py の TestSiteFor と対になるテストにしてある。
"""

import pytest

from comken.exceptions import SalesforceSiteNotFoundError
from comken.services.salesforce_downloader.browser_sites import (
    BROWSER_SITES,
    SolutionBrowser,
    SolutionSandboxBrowser,
    browser_site_for,
)
from comken.toolbox.browser.sites import SITES as LIBRARY_SITES
from comken.toolbox.browser.sites.salesforce import Salesforce
from comken.toolbox.salesforce.sites import Solution, SolutionSandbox


class TestOrgClasses:
    """組織ごとのブラウザサイトクラス — URLはAPI側のDOMAIN_URLをそのまま使う。"""

    def test_solution_browser_uses_api_side_domain(self):
        assert SolutionBrowser.BASE_URL == Solution.DOMAIN_URL

    def test_solution_sandbox_browser_uses_api_side_domain(self):
        assert SolutionSandboxBrowser.BASE_URL == SolutionSandbox.DOMAIN_URL

    def test_org_classes_have_distinct_names(self):
        """PROFILE_ROOT/<NAME>/ でログイン状態が分かれるため、NAME は必ず別にする。"""
        names = [site.NAME for site in BROWSER_SITES]
        assert len(names) == len(set(names))

    def test_not_registered_as_library_sites(self):
        """ダミーURLの雛形(comken.toolbox.browser.sites.Salesforce)とは別物。"""
        for site in BROWSER_SITES:
            assert site not in LIBRARY_SITES

    def test_org_classes_are_salesforce_browser_sites(self):
        for site in BROWSER_SITES:
            assert issubclass(site, Salesforce)


class TestBrowserSiteFor:
    """レポートの URL から、ブラウザ経由でつなぐ組織を決める。"""

    def test_url_of_a_registered_org(self):
        url = f"{SolutionSandboxBrowser.BASE_URL}/lightning/r/Report/00O5g00000ABCDE/view"
        assert browser_site_for(url) is SolutionSandboxBrowser

    def test_host_case_is_ignored(self):
        assert browser_site_for(SolutionSandboxBrowser.BASE_URL.upper()) is SolutionSandboxBrowser

    def test_surrounding_spaces_are_ignored(self):
        url = f"  {SolutionSandboxBrowser.BASE_URL}/lightning  "
        assert browser_site_for(url) is SolutionSandboxBrowser

    def test_unknown_domain_raises(self):
        with pytest.raises(SalesforceSiteNotFoundError) as error:
            browser_site_for("https://other.my.salesforce.com/lightning/r/Report/00O/view")
        assert SolutionSandboxBrowser.BASE_URL in str(error.value)

    def test_report_id_alone_raises(self):
        with pytest.raises(SalesforceSiteNotFoundError):
            browser_site_for("00O5g00000ABCDE")

    def test_empty_raises(self):
        with pytest.raises(SalesforceSiteNotFoundError):
            browser_site_for("")
