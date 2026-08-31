"""comken/toolbox/salesforce/sites/sandbox.py — Sandbox 組織

※ URL は**ダミー**。配置するときに実際の値へ書き換える（詳細は sites/__init__.py）。

この組織でしか通じないもの（レポート ID・オブジェクトの API 参照名・独自の手順）を
ここに置く。共通の操作は `SalesforceBase` 側にあるので書かない。
"""

from comken.toolbox.salesforce.client import SalesforceBase


class Sandbox(SalesforceBase):
    """Sandbox 組織のクライアント。

    使い方:
        with Sandbox() as sf:
            rows = sf.report.get("00O...")
    """

    # comken 配下の組織クラスは、管理者が昇格を判断した印として OWNER = "comken" を書く。
    # プロジェクト側で定義した組織クラスは「プロジェクト名 / 担当者」の形式で書く。
    OWNER = "comken"

    # My Domain の URL。Sandbox は「<組織>--<サンドボックス名>.sandbox」の形になる。
    # 組織で固定なので config.ini には置かない（環境で変わる値だけを config.ini へ）
    # TODO: 配置するときに実際の URL へ置き換える
    DOMAIN_URL = "https://example--sandbox.sandbox.my.salesforce.com"

    # 認証情報のキー名の頭。DPAPI には sandbox_client_id / sandbox_client_secret で入る。
    # 別の登録に切り替えるときだけ Sandbox(prefix=...) で渡す
    CREDENTIAL_PREFIX = "sandbox"

    # 組織が対応している API バージョン。既定と違うときだけ上書きする
    # API_VERSION = "67.0"
