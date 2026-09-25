"""comken.toolbox.browser.sites.salesforce のテスト。

comken.toolbox.salesforce.sites.site_for() のブラウザ版。判定方法が同じなので、
tests/test_salesforce.py の TestSiteFor と対になるテストにしてある。
"""

import pytest

from comken.exceptions import SalesforceError
from comken.toolbox.browser.sites.salesforce import (
    SITES,
    SalesforceReportBrowser,
    Solution,
    SolutionSandbox,
    site_for,
)
from comken.toolbox.salesforce.sites import Solution as SolutionApi
from comken.toolbox.salesforce.sites import SolutionSandbox as SolutionSandboxApi


class TestOrgClasses:
    """組織ごとのブラウザサイトクラス — URLはAPI側のDOMAIN_URLをそのまま使う。"""

    def test_solution_uses_api_side_domain(self):
        assert Solution.BASE_URL == SolutionApi.DOMAIN_URL

    def test_solution_sandbox_uses_api_side_domain(self):
        assert SolutionSandbox.BASE_URL == SolutionSandboxApi.DOMAIN_URL

    def test_solution_uses_api_side_credential_prefix(self):
        assert Solution.CREDENTIAL_PREFIX == SolutionApi.CREDENTIAL_PREFIX

    def test_org_classes_have_distinct_names(self):
        """PROFILE_ROOT/<NAME>/ でログイン状態が分かれるため、NAME は必ず別にする。"""
        names = [site.NAME for site in SITES]
        assert len(names) == len(set(names))

    def test_org_classes_are_salesforce_browser_sites(self):
        for site in SITES:
            assert issubclass(site, SalesforceReportBrowser)


class TestSiteFor:
    """レポートの URL から、ブラウザ経由でつなぐ組織を決める。"""

    def test_url_of_a_registered_org(self):
        url = f"{SolutionSandbox.BASE_URL}/lightning/r/Report/00O5g00000ABCDE/view"
        assert site_for(url) is SolutionSandbox

    def test_host_case_is_ignored(self):
        assert site_for(SolutionSandbox.BASE_URL.upper()) is SolutionSandbox

    def test_surrounding_spaces_are_ignored(self):
        url = f"  {SolutionSandbox.BASE_URL}/lightning  "
        assert site_for(url) is SolutionSandbox

    def test_unknown_domain_raises(self):
        with pytest.raises(SalesforceError) as error:
            site_for("https://other.my.salesforce.com/lightning/r/Report/00O/view")
        assert SolutionSandbox.BASE_URL in str(error.value)

    def test_report_id_alone_raises(self):
        with pytest.raises(SalesforceError):
            site_for("00O5g00000ABCDE")

    def test_empty_raises(self):
        with pytest.raises(SalesforceError):
            site_for("")
