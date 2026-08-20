"""comken/toolbox/salesforce/direct/adapter.py — Direct 版 SiteBase Adapter。

comken オリジナル (`direct/`) の `SalesforceBase` を `SiteBase` 共通
インターフェースに明示的に合わせる薄い Adapter。組織クラス
(`sites/sandbox.py` 等) の継承元を `SalesforceBase` 直接から
`DirectSiteBase` に置き換えるだけで、「direct 版か社内ライブラリ版か」
をサブクラス切替で組めるようになる。
"""

from comken.toolbox.salesforce.direct.client import SalesforceBase
from comken.toolbox.salesforce.sitebase import SiteBase


class DirectSiteBase(SalesforceBase, SiteBase):
    """Direct 版の SiteBase 実装。

    `SalesforceBase` の API が `SiteBase` プロトコルを自然に満たしているので、
    追加実装は持たない。「`SiteBase` 契約を満たす direct 実装である」という
    宣言だけが役割。
    """
