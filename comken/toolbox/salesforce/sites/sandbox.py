"""comken/toolbox/salesforce/sites/sandbox.py — Sandbox 組織

※ 組織固有の値（My Domain・レポート ID）は `comken/settings.py` にある。
配置時に書き換えるのはそちらで、このファイルは触らない。

この組織でしか通じないもの（レポート ID・オブジェクトの API 参照名・独自の手順）を
ここに置く。共通の操作は `SalesforceBase` 側にあるので書かない。
"""

from .... import settings
from ..client import SalesforceBase


class Sandbox(SalesforceBase):
    """Sandbox 組織のクライアント。

    使い方:
        with Sandbox() as sf:
            rows = sf.案件一覧()
    """

    # 組織で固定の値は comken/settings.py にまとめる（社内の値を持つファイルを1つにする）
    DOMAIN_URL = settings.SANDBOX_DOMAIN_URL

    # 認証情報のキー名の頭。DPAPI には sandbox_client_id / sandbox_client_secret で入る。
    # 別の登録に切り替えるときだけ Sandbox(prefix=...) で渡す
    CREDENTIAL_PREFIX = settings.SANDBOX_CREDENTIAL_PREFIX

    # 組織が対応している API バージョン。既定と違うときだけ上書きする
    # API_VERSION = "67.0"

    # レポート ID は組織ごとに固有で、環境では変わらない
    REPORT_案件一覧 = settings.SANDBOX_REPORT_案件一覧

    def 案件一覧(self) -> list[dict]:
        """案件一覧レポートの明細を返す。

        2000 行を超えると SalesforceReportTruncatedError で止まる。
        超えるようになったら、期間で区切るか SOQL へ移す。
        """
        return self.report.run(self.REPORT_案件一覧)
