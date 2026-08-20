"""comken/toolbox/salesforce/sitebase.py — 組織クラスの共通基底。

社内ライブラリと comken オリジナル (`direct/`) で API の使い方が違うため、
利用者から見たインタフェースをここで共通化する。サブクラス
(`DirectSiteBase` / `InternalSiteBase`) が API の差分を吸収し、
組織クラス側 (`sites/sandbox.py` 等) は SiteBase だけを継承すればよくなる。

    from comken.toolbox.salesforce.sitebase import SiteBase

    # 組織クラス
    class Sandbox(SiteBase):
        DOMAIN_URL = "..."
        CREDENTIAL_PREFIX = "sandbox"

`SiteBase` 自体は `Protocol` なので、抽象メソッドの強制はせず、
具象サブクラスが SiteBase 契約を満たすという形式にする。
"""

from typing import Protocol


class SiteBase(Protocol):
    """組織クラス (Sandbox / Production / Developer) の共通基底。

    実装は以下の 2 系統が将来切り替わる:
    - `DirectSiteBase` (`comken.toolbox.salesforce.direct.adapter`) — comken オリジナル
    - `InternalSiteBase` (`comken.toolbox.salesforce.internal`)       — 社内ライブラリ用 (future)
    """

    # 組織で固定の値。config.ini には置かない (環境で変わる値だけを config.ini へ)
    DOMAIN_URL: str
    # DPAPI に保存された認証情報のキー名の頭
    CREDENTIAL_PREFIX: str

    def request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        component: str = "",
    ) -> tuple[dict | list | str | None, dict]:
        """HTTP リクエストを送り、 (レスポンス本文, レスポンスヘッダー) を返す。"""
        ...

    def data_path(self, path: str) -> str:
        """相対パスを data API のエンドポイント URL に変換する。"""
        ...

    def query(self, soql: str) -> list[dict]:
        """SOQL クエリを実行し、結果を list[dict] で返す。"""
        ...
