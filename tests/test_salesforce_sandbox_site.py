"""``site_for(url, sandbox=True)``（本番の URL からサンドボックスの組織を引く）のテスト。

API 側（``comken.toolbox.salesforce.sites``）とブラウザ側
（``comken.toolbox.browser.sites.salesforce``）の両方が、同じ規則で動くことを確かめる。
"""

from __future__ import annotations

import pytest

from comken.exceptions import SalesforceError
from comken.toolbox.browser.sites import salesforce as browser_sites
from comken.toolbox.salesforce import sites as api_sites
from comken.toolbox.salesforce.hosts import host_of

REPORT_PATH = "/lightning/r/Report/00O5g00000ABCDEfgh/view"
PRODUCTION_URL = f"https://example.my.salesforce.com{REPORT_PATH}"
SANDBOX_URL = f"https://example--sandbox.sandbox.my.salesforce.com{REPORT_PATH}"

BOTH_SIDES = pytest.mark.parametrize("sites", [api_sites, browser_sites], ids=["api", "browser"])


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (PRODUCTION_URL, "example.my.salesforce.com"),
        # ブラウザのアドレスバーの URL（Lightning）は My Domain の形に読み替える
        (f"https://example.lightning.force.com{REPORT_PATH}", "example.my.salesforce.com"),
        (
            f"https://example--sandbox.sandbox.lightning.force.com{REPORT_PATH}",
            "example--sandbox.sandbox.my.salesforce.com",
        ),
        # 大文字小文字・前後の空白は無視する
        (f"  HTTPS://Example.My.Salesforce.com{REPORT_PATH}  ", "example.my.salesforce.com"),
        # ほかのホストはそのまま
        ("https://other.example.com/x", "other.example.com"),
    ],
)
def test_host_of_normalizes_lightning_to_my_domain(url: str, expected: str) -> None:
    assert host_of(url) == expected


@BOTH_SIDES
def test_default_returns_the_organization_of_the_url(sites) -> None:
    assert sites.site_for(PRODUCTION_URL).__name__ == "Solution"
    assert sites.site_for(SANDBOX_URL).__name__ == "SolutionSandbox"


@BOTH_SIDES
def test_sandbox_true_returns_sandbox_of_production_url(sites) -> None:
    assert sites.site_for(PRODUCTION_URL, sandbox=True).__name__ == "SolutionSandbox"


@BOTH_SIDES
def test_sandbox_true_keeps_a_url_that_is_already_sandbox(sites) -> None:
    assert sites.site_for(SANDBOX_URL, sandbox=True).__name__ == "SolutionSandbox"


@BOTH_SIDES
def test_lightning_urls_are_read_as_the_same_organization(sites) -> None:
    production = f"https://example.lightning.force.com{REPORT_PATH}"
    sandbox = f"https://example--sandbox.sandbox.lightning.force.com{REPORT_PATH}"

    assert sites.site_for(production).__name__ == "Solution"
    assert sites.site_for(production, sandbox=True).__name__ == "SolutionSandbox"
    assert sites.site_for(sandbox).__name__ == "SolutionSandbox"


@BOTH_SIDES
def test_unknown_organization_is_an_error_even_with_sandbox(sites) -> None:
    with pytest.raises(SalesforceError, match="組織が登録されていません"):
        sites.site_for("https://other.my.salesforce.com/x", sandbox=True)


@BOTH_SIDES
def test_sandbox_true_without_a_registered_sandbox_is_an_error(sites, monkeypatch) -> None:
    production = sites.site_for(PRODUCTION_URL)
    monkeypatch.setattr(production, "SANDBOX_SITE", None)

    with pytest.raises(SalesforceError, match="対応するサンドボックスが登録されていません"):
        sites.site_for(PRODUCTION_URL, sandbox=True)
    # sandbox=False（既定）には影響しない
    assert sites.site_for(PRODUCTION_URL) is production


def test_api_and_browser_pairings_point_at_matching_organizations() -> None:
    """API 側とブラウザ側で、本番と対のサンドボックスが同じ組織を指す。"""
    api_pair = api_sites.site_for(PRODUCTION_URL), api_sites.site_for(PRODUCTION_URL, sandbox=True)
    browser_pair = (
        browser_sites.site_for(PRODUCTION_URL),
        browser_sites.site_for(PRODUCTION_URL, sandbox=True),
    )

    assert [site.__name__ for site in api_pair] == [site.__name__ for site in browser_pair]
    assert browser_pair[1].BASE_URL == api_pair[1].DOMAIN_URL
