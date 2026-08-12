"""
salesforce/sites/site_c.py — SiteC 組織

※ SiteC は仮名。配置時に実際の組織名へ書き換える（詳細は sites/__init__.py）。
"""

from ..client import Salesforce


class SiteC(Salesforce):
    """SiteC 組織のクライアント。

    使い方:
        with SiteC(
            client_id=cred.client_id,
            client_secret=cred.client_secret,
            domain_url=config.SITE_C.DOMAIN_URL,
        ) as sf:
            rows = sf.案件一覧()
    """

    CREDENTIAL_PREFIX = "site_c"
    CONFIG_SECTION = "SITE_C"

    REPORT_案件一覧 = "00O000000000003"  # TODO: 実際のレポート ID に置き換える

    def 案件一覧(self) -> list[dict]:
        """案件一覧レポートの明細を返す。"""
        return self.report.run(self.REPORT_案件一覧)
