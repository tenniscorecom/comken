"""comken/toolbox/salesforce/browser/sites/solution_sandbox.py — Sandbox組織のブラウザアクセス。

※ URL はAPI版の組織クラス（``comken.toolbox.salesforce.sites.solution_sandbox.SolutionSandbox``）が
持つ ``DOMAIN_URL`` をそのまま使う（同じURLを二重に書かない）。実際の値の書き換えは
そちら1箇所で済む。
"""

from comken.toolbox.salesforce.browser.site import Salesforce
from comken.toolbox.salesforce.sites.solution_sandbox import (
    SolutionSandbox as _SolutionSandboxApi,
)


class SolutionSandbox(Salesforce):
    """Solution Sandbox組織へのブラウザ経由アクセス。

    使い方:
        with SolutionSandbox() as sf:
            sf.login_with_credentials()  # prefix省略 → CREDENTIAL_PREFIXを使う
            sf.wait_for_manual_login()
            for report_id, path in sf.export_reports(reports):
                ...
    """

    NAME = "salesforce_solution_sandbox"
    BASE_URL = _SolutionSandboxApi.DOMAIN_URL
    CREDENTIAL_PREFIX = _SolutionSandboxApi.CREDENTIAL_PREFIX
    OWNER = "comken"
