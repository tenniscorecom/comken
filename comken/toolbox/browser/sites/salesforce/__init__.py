"""comken/toolbox/browser/sites/salesforce/__init__.py — Salesforceのブラウザ経由ダウンロード。

comken.toolbox.salesforce（API版）の Reports and Dashboards REST API は2000行が
上限のため（詳しくは docs/salesforce.md）、それを超えるレポートは画面のエクスポート
機能をブラウザ経由で叩いて取るしかない。ここはその手段を提供する。

``Salesforce`` は雛形（``BASE_URL`` がダミー）なので、実際の組織別の値（URL・認証
情報名）は ``Solution`` / ``SolutionSandbox`` が API 側の組織クラス
（``comken.toolbox.salesforce.sites``）の ``DOMAIN_URL`` / ``CREDENTIAL_PREFIX`` を
そのまま使う（同じ URL を二重に書かない）。

    from comken.toolbox.browser.sites.salesforce import site_for

    site_class = site_for(report_url)
    with site_class() as sf:
        sf.login_with_credentials()  # prefix省略 → CREDENTIAL_PREFIXを使う
        sf.wait_for_manual_login()
        for report_id, path in sf.export_reports(reports):
            print(report_id, path)

組織を増やすときは、このフォルダにファイルを1つ足して ``Salesforce`` を継承し、
``SITES`` にも登録する。
"""

from urllib.parse import urlsplit

from comken.exceptions import SalesforceSiteNotFoundError
from comken.toolbox.browser.sites.salesforce.site import Salesforce
from comken.toolbox.browser.sites.salesforce.solution import Solution
from comken.toolbox.browser.sites.salesforce.solution_sandbox import SolutionSandbox

# 登録済みの組織。URL からどの組織へつなぐかを引くのに使う。
# **組織を増やしたらここにも足す。** 足し忘れると、その組織の URL だけが
# SalesforceSiteNotFoundError になる（黙って別組織へつなぐことはない）
SITES: tuple[type[Salesforce], ...] = (Solution, SolutionSandbox)

__all__ = ["Salesforce", "Solution", "SolutionSandbox", "SITES", "site_for"]


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
