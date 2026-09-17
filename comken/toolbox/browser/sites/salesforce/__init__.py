"""comken/toolbox/browser/sites/salesforce/__init__.py — Salesforceレポートのブラウザダウンロード。

comken.toolbox.salesforce の Reports and Dashboards REST API は2000行が上限のため
（詳しくは docs/salesforce.md）、それを超えるレポートは画面のエクスポート機能を
ブラウザ経由で叩いて取るしかない。ここはその手段を提供する。

    from comken.toolbox.browser.sites.salesforce import Salesforce

    with Salesforce() as sf:
        sf.login_with_token(access_token, instance_url)
        for report_id, path in sf.export_reports(report_urls, "出力先"):
            print(report_id, path)

access_token / instance_url は comken.toolbox.salesforce 側で取得したものをそのまま渡す
（例: SalesforceBase.access_token / .instance_url）。
"""

from comken.toolbox.browser.sites.salesforce.site import Salesforce

__all__ = ["Salesforce"]
