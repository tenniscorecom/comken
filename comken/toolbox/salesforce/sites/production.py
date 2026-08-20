"""comken/toolbox/salesforce/sites/production.py — Production 組織

※ URL とレポート ID は**ダミー**。配置するときに実際の値へ書き換える
（詳細は sites/__init__.py）。

この組織でしか通じないもの（レポート ID・オブジェクトの API 参照名・独自の手順）を
ここに置く。共通の操作は `SalesforceBase` 側にあるので書かない。
"""

from comken.toolbox.salesforce.client import SalesforceBase


class Production(SalesforceBase):
    """Production 組織のクライアント。

    使い方:
        with Production() as sf:
            rows = sf.opportunities()
    """

    # comken 配下の組織クラスは、管理者が昇格を判断した印として OWNER = "comken" を書く。
    # プロジェクト側で定義した組織クラスは「プロジェクト名 / 担当者」の形式で書く。
    OWNER = "comken"

    # My Domain の URL。Production は「<組織>.my」の形になる。
    # 組織で固定なので config.ini には置かない（環境で変わる値だけを config.ini へ）
    # TODO: 配置するときに実際の URL へ置き換える
    DOMAIN_URL = "https://example.my.salesforce.com"

    # 認証情報のキー名の頭。DPAPI には production_client_id / production_client_secret で入る。
    # 別の登録に切り替えるときだけ Production(prefix=...) で渡す
    CREDENTIAL_PREFIX = "production"

    # 組織が対応している API バージョン。既定と違うときだけ上書きする
    # API_VERSION = "67.0"

    # レポート ID は組織ごとに固有で、環境では変わらない
    # TODO: 配置するときに実際のレポート ID へ置き換える
    REPORT_OPPORTUNITIES = "00O000000000002"

    def opportunities(self) -> list[dict]:
        """案件一覧レポートの明細を返す。

        2000 行を超えると SalesforceReportTruncatedError で止まる。
        超えるようになったら、期間で区切るか SOQL へ移す。
        """
        return self.report.run(self.REPORT_OPPORTUNITIES)
