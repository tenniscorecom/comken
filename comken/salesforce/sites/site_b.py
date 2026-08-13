"""
salesforce/sites/site_b.py — SiteB 組織

※ SiteB は仮名。配置時に実際の組織名へ書き換える（詳細は sites/__init__.py）。
"""

from ..client import Salesforce


class SiteB(Salesforce):
    """SiteB 組織のクライアント。

    使い方:
        with SiteB.from_credentials(config.SITE_B.DOMAIN_URL) as sf:
            rows = sf.案件一覧()
    """

    CREDENTIAL_PREFIX = "site_b"
    CONFIG_SECTION = "SITE_B"

    REPORT_案件一覧 = "00O000000000002"  # TODO: 実際のレポート ID に置き換える

    def 案件一覧(self) -> list[dict]:
        """案件一覧レポートの明細を返す。"""
        return self.report.run(self.REPORT_案件一覧)
