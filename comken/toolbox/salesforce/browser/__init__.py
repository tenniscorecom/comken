"""comken/toolbox/salesforce/browser/__init__.py — Salesforceレポートのブラウザ経由ダウンロード。

comken.toolbox.salesforce（API版）の Reports and Dashboards REST API は2000行が
上限のため（詳しくは docs/salesforce.md）、それを超えるレポートは画面のエクスポート
機能をブラウザ経由で叩いて取るしかない。ここはその手段を提供する。

組織ごとのクラス（``Solution``・``SolutionSandbox``）は
``comken.toolbox.salesforce.browser.sites`` にある。

    from comken.toolbox.salesforce.browser.sites import site_for

    site_class = site_for(report_url)
    with site_class() as sf:
        sf.login_with_credentials(site_class.CREDENTIAL_PREFIX)
        sf.wait_for_manual_login()
        for report_id, path in sf.export_reports(reports):
            print(report_id, path)
"""

from comken.toolbox.salesforce.browser.site import Salesforce

__all__ = ["Salesforce"]
