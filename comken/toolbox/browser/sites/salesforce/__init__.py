"""comken/toolbox/browser/sites/salesforce/__init__.py — Salesforceのブラウザ経由ダウンロード。

comken.toolbox.salesforce（API版）の Reports and Dashboards REST API は2000行が
上限のため（詳しくは docs/salesforce.md）、それを超えるレポートは画面のエクスポート
機能をブラウザ経由で叩いて取るしかない。ここはその手段を提供する。

``SalesforceSiteBase`` は雛形（``BASE_URL`` がダミー）なので、実際の組織別の値
（URL・認証情報名）は ``SolutionSite`` / ``SolutionSandboxSite`` が API 側の組織
クラス（``comken.toolbox.salesforce.sites``）の ``DOMAIN_URL`` / ``CREDENTIAL_PREFIX``
をそのまま使う（同じ URL を二重に書かない）。

    from comken.toolbox.browser.sites.salesforce import site_for

    site_class = site_for(report_url)
    with site_class() as sf:
        sf.login_with_credentials()  # prefix省略 → CREDENTIAL_PREFIXを使う
        sf.wait_for_manual_login()
        for report_id, path in sf.export_reports(reports):
            print(report_id, path)

組織を増やすときは、このフォルダにファイルを1つ足して ``SalesforceSiteBase`` を
継承し、``registry.py`` の ``SITES`` にも登録する。
"""

from comken.toolbox.browser.sites.salesforce.base import SalesforceSiteBase
from comken.toolbox.browser.sites.salesforce.registry import SITES, site_for
from comken.toolbox.browser.sites.salesforce.solution import SolutionSite
from comken.toolbox.browser.sites.salesforce.solution_sandbox import SolutionSandboxSite

__all__ = [
    "SalesforceSiteBase",
    "SolutionSite",
    "SolutionSandboxSite",
    "SITES",
    "site_for",
]
