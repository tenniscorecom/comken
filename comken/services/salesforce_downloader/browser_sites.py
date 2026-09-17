"""comken/services/salesforce_downloader/browser_sites.py — 組織ごとのブラウザ経由Salesforce。

レポートAPIの2000行上限を超えるレポート（マトリックス／統合などSOQLに書き換えられ
ない形式）向けの最終手段（詳しくは docs/salesforce.md）。

``comken.toolbox.browser.sites.salesforce.Salesforce`` は雛形（BASE_URLがダミー）の
ままなので、組織ごとの実際の値はここで持つ。URLは
``comken.toolbox.salesforce.sites`` の組織クラス（``Solution``・``SolutionSandbox``）が
既に持っている ``DOMAIN_URL`` をそのまま使う（同じURLを二重に書かない）。

``toolbox.browser`` と ``toolbox.salesforce`` は互いに依存しない設計
（``tests/test_layers.py``）だが、``services`` はどちらにも依存してよい層なので、
組織ごとの組み合わせはここに置く。

    from comken.services.salesforce_downloader.browser_sites import browser_site_for

    site_class = browser_site_for(report_url)
    with site_class() as sf:
        sf.login_with_credentials(site_class.CREDENTIAL_PREFIX)
        sf.wait_for_manual_login()
        for report_id, path in sf.export_reports(reports):
            ...

組織を増やすときは、このファイルにクラスを1つ足して ``BROWSER_SITES`` にも登録する。
"""

from urllib.parse import urlsplit

from comken.exceptions import SalesforceSiteNotFoundError
from comken.toolbox.browser.sites.salesforce import Salesforce
from comken.toolbox.salesforce.sites import Solution, SolutionSandbox


class SolutionBrowser(Salesforce):
    """Solution組織へのブラウザ経由アクセス。"""

    NAME = "salesforce_solution"
    BASE_URL = Solution.DOMAIN_URL
    OWNER = "comken"


class SolutionSandboxBrowser(Salesforce):
    """Solution Sandbox組織へのブラウザ経由アクセス。"""

    NAME = "salesforce_solution_sandbox"
    BASE_URL = SolutionSandbox.DOMAIN_URL
    OWNER = "comken"


# 登録済みの組織。URL からどの組織へつなぐかを引くのに使う。
# **組織を増やしたらここにも足す。** 足し忘れると、その組織の URL だけが
# SalesforceSiteNotFoundError になる（黙って別組織へつなぐことはない）
BROWSER_SITES: tuple[type[Salesforce], ...] = (SolutionBrowser, SolutionSandboxBrowser)

__all__ = ["BROWSER_SITES", "SolutionBrowser", "SolutionSandboxBrowser", "browser_site_for"]


def browser_site_for(url: str) -> type[Salesforce]:
    """レポートのURLから、ブラウザ経由でつなぐ組織のクラスを返す。

    ``comken.toolbox.salesforce.sites.site_for()`` のブラウザ版。判定方法
    （URLのドメイン一致）も同じ。

        browser_site_for("https://example.my.salesforce.com/lightning/...")
        # → SolutionBrowser

    Args:
        url: レポートを開いたときのアドレス。**ドメインを含む URL であること**
            （レポート ID だけでは、どの組織のものか決められない）。

    Raises:
        SalesforceSiteNotFoundError: 登録済みのどの組織にも当てはまらない場合。
    """
    host = _host_of(url)
    for site in BROWSER_SITES:
        if host and _host_of(site.BASE_URL) == host:
            return site
    raise SalesforceSiteNotFoundError(url, [site.BASE_URL for site in BROWSER_SITES])


def _host_of(url: str) -> str:
    """URL からホスト名だけを取り出す（大文字小文字の違いは無視する）。"""
    return urlsplit(url.strip()).netloc.lower()
