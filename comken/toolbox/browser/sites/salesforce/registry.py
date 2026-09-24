"""comken/toolbox/browser/sites/salesforce/registry.py — ブラウザ版 Salesforce の組織登録。

``comken.toolbox.salesforce.sites`` のブラウザ版。判定方法（URLのドメイン一致）も同じ。

    from comken.toolbox.browser.sites.salesforce import site_for

    site_class = site_for(report_url)
    with site_class() as sf:
        sf.export_reports(...)
"""

from urllib.parse import urlsplit

from comken.exceptions import SalesforceSiteNotFoundError
from comken.toolbox.browser.sites.salesforce.base import SalesforceSiteBase
from comken.toolbox.browser.sites.salesforce.solution import SolutionSite
from comken.toolbox.browser.sites.salesforce.solution_sandbox import SolutionSandboxSite

# 登録済みの組織。URL からどの組織へつなぐかを引くのに使う。
# **組織を増やしたらここにも足す。** 足し忘れると、その組織の URL だけが
# SalesforceSiteNotFoundError になる（黙って別組織へつなぐことはない）
SITES: tuple[type[SalesforceSiteBase], ...] = (SolutionSite, SolutionSandboxSite)


def site_for(url: str) -> type[SalesforceSiteBase]:
    """レポートのURLから、ブラウザ経由でつなぐ組織のクラスを返す。

    ``comken.toolbox.salesforce.sites.site_for()`` のブラウザ版。判定方法
    （URLのドメイン一致）も同じ。

        site_for("https://example.my.salesforce.com/lightning/...")
        # → SolutionSite

    Args:
        url: レポートを開いたときのアドレス。**ドメインを含む URL であること**
            （レポート ID だけでは、どの組織のものか決められない）。

    Raises:
        SalesforceSiteNotFoundError: 登録済みのどの組織にも当てはまらない場合。
    """
    host = _host_of(url)
    for site in SITES:
        if host and _host_of(site.BASE_URL) == host:
            return site
    raise SalesforceSiteNotFoundError(url, [site.BASE_URL for site in SITES])


def _host_of(url: str) -> str:
    """URL からホスト名だけを取り出す（大文字小文字の違いは無視する）。"""
    return urlsplit(url.strip()).netloc.lower()
