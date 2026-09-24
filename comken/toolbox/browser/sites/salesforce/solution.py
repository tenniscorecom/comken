"""comken/toolbox/browser/sites/salesforce/solution.py — Solution組織へのブラウザ経由アクセス。

※ URL はAPI版の組織クラス（``comken.toolbox.salesforce.sites.solution.Solution``）が
持つ ``DOMAIN_URL`` をそのまま使う（同じURLを二重に書かない）。実際の値の書き換えは
そちら1箇所で済む。

※ クラス名は API 側（``comken.toolbox.salesforce.sites.Solution``）と同名。
   パッケージ（``comken.toolbox.browser.sites.salesforce`` と
   ``comken.toolbox.salesforce.sites``）で区別する。
"""

from comken.toolbox.browser.sites.salesforce.base import SalesforceReportBrowser
from comken.toolbox.salesforce.sites.solution import Solution as _SolutionApi


class Solution(SalesforceReportBrowser):
    """Solution組織へのブラウザ経由アクセス。

    使い方:
        with Solution() as sf:
            sf.login_with_credentials()  # prefix省略 → CREDENTIAL_PREFIXを使う
            sf.wait_for_manual_login()
            for report_id, path in sf.export_reports(reports):
                ...
    """

    NAME = "salesforce_solution"
    BASE_URL = _SolutionApi.DOMAIN_URL
    CREDENTIAL_PREFIX = _SolutionApi.CREDENTIAL_PREFIX
    OWNER = "comken"
