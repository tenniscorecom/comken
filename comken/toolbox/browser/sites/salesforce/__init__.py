"""comken/toolbox/browser/sites/salesforce/__init__.py — Salesforceレポートのブラウザダウンロード。

comken.toolbox.salesforce の Reports and Dashboards REST API は2000行が上限のため
（詳しくは docs/salesforce.md）、それを超えるレポートは画面のエクスポート機能を
ブラウザ経由で叩いて取るしかない。ここはその手段を提供する。

    from comken.toolbox.browser.sites.salesforce import Salesforce

    with Salesforce() as sf:
        sf.go_login()
        sf.wait_for_manual_login()
        reports = {report_url: f"出力先/{report_id}.csv" for report_url, report_id in ...}
        for report_id, path in sf.export_reports(reports):
            print(report_id, path)
"""

from comken.toolbox.browser.sites.salesforce.site import Salesforce

__all__ = ["Salesforce"]
