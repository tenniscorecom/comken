"""
salesforce/sites/site_a.py — SiteA 組織

※ SiteA は仮名。配置時に実際の組織名へ書き換える（詳細は sites/__init__.py）。

この組織でしか通じないもの（レポート ID・オブジェクトの API 参照名・独自の手順）を
ここに置く。共通の操作は `Salesforce` 側にあるので書かない。
"""

from ..client import Salesforce


class SiteA(Salesforce):
    """SiteA 組織のクライアント。

    使い方:
        with SiteA.from_credentials(config.SITE_A.DOMAIN_URL) as sf:
            rows = sf.案件一覧()
    """

    # 認証情報のキー名の頭。DPAPI には site_a_client_id / site_a_client_secret で入る。
    # 本番とテストを切り替えるときは from_credentials(prefix=...) に config.ini から渡す
    CREDENTIAL_PREFIX = "site_a"

    # My Domain の URL を書く config.ini のセクション名
    CONFIG_SECTION = "SITE_A"

    # 組織が対応している API バージョン。既定と違うときだけ上書きする
    # API_VERSION = "60.0"

    # レポート ID は組織ごとに固有で、環境で変わらないのでここに書く。
    # 環境で変わる値（URL・出力先フォルダ）だけを config.ini に置く
    REPORT_案件一覧 = "00O000000000001"  # TODO: 実際のレポート ID に置き換える

    def 案件一覧(self) -> list[dict]:
        """案件一覧レポートの明細を返す。

        2000 行を超えると SalesforceReportTruncatedError で止まる。
        超えるようになったら、期間で区切るか SOQL へ移す。
        """
        return self.report.run(self.REPORT_案件一覧)
