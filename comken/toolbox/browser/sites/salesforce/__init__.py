"""comken/toolbox/browser/sites/salesforce/__init__.py — Salesforceレポートのブラウザダウンロード。

comken.toolbox.salesforce の Reports and Dashboards REST API は2000行が上限のため
（詳しくは docs/salesforce.md）、それを超えるレポートは画面のエクスポート機能を
ブラウザ経由で叩いて取るしかない。ここはその手段を提供する。

    from comken.toolbox.browser.sites.salesforce import Salesforce

    with Salesforce() as sf:
        sf.go_login()
        sf.wait_for_manual_login()
        for report_id, path in sf.export_reports(report_urls, "出力先"):
            print(report_id, path)
"""

from comken.toolbox.browser.sites.salesforce.site import Salesforce

__all__ = ["Salesforce"]
