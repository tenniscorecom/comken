"""comken/toolbox/salesforce/browser/sites/__init__.py — 組織ごとのブラウザ経由Salesforce。

``comken.toolbox.salesforce.sites``（API版の組織クラス）と対になる、
ブラウザ版の組織クラス。``comken.toolbox.salesforce.browser.site.Salesforce`` は
雛形（BASE_URLがダミー）のままなので、組織ごとの実際の値はここで持つ。
URLはAPI版の組織クラスが既に持っている ``DOMAIN_URL`` をそのまま使う
（同じURLを二重に書かない）。

    from comken.toolbox.salesforce.browser.sites import site_for

    site_class = site_for(report_url)
    with site_class() as sf:
        sf.login_with_credentials()  # prefix省略 → CREDENTIAL_PREFIXを使う
        sf.wait_for_manual_login()
        for report_id, path in sf.export_reports(reports):
            ...

組織を増やすときは、このフォルダにファイルを1つ足して
``comken.toolbox.salesforce.browser.site.Salesforce`` を継承し、``SITES`` にも登録する。
"""

from urllib.parse import urlsplit

from comken.exceptions import SalesforceSiteNotFoundError
from comken.toolbox.salesforce.browser.site import Salesforce
from comken.toolbox.salesforce.browser.sites.solution import Solution
from comken.toolbox.salesforce.browser.sites.solution_sandbox import SolutionSandbox

# 登録済みの組織。URL からどの組織へつなぐかを引くのに使う。
# **組織を増やしたらここにも足す。** 足し忘れると、その組織の URL だけが
# SalesforceSiteNotFoundError になる（黙って別組織へつなぐことはない）
SITES: tuple[type[Salesforce], ...] = (Solution, SolutionSandbox)

__all__ = ["SITES", "Solution", "SolutionSandbox", "site_for"]


def site_for(url: str) -> type[Salesforce]:
    """レポートのURLから、ブラウザ経由でつなぐ組織のクラスを返す。

    ``comken.toolbox.salesforce.sites.site_for()`` のブラウザ版。判定方法
    （URLのドメイン一致）も同じ。

        site_for("https://example.my.salesforce.com/lightning/...")
        # → Solution

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
