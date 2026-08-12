"""組織（サイト）ごとの Salesforce クライアント。

組織は My Domain の URL が違うので、1組織につき1クラス・1インスタンスにする。
共通の操作（SOQL・CRUD・レポート・計測）は `Salesforce` が持っているので、
ここに書くのは**その組織でしか通じないもの**だけにする。

    from comken.salesforce.sites import SiteA

    with SiteA(
        client_id=..., client_secret=..., domain_url=config.SITE_A.DOMAIN_URL
    ) as sf:
        rows = sf.未処理の申請()

3組織をまとめて回すときは SITES を使う:

    from comken.salesforce.sites import SITES

    for site_class in SITES:
        secrets = 認証情報(site_class.CREDENTIAL_PREFIX)
        with site_class(**secrets, domain_url=ドメイン(site_class)) as sf:
            ...

> [!warning] サイト名は仮名
> **このリポジトリは公開しているので、実際の組織名を書かない。**
> `SiteA` / `SiteB` / `SiteC` は仮名で、共有サーバーへ配置するときに
> 実際の組織名へ書き換える（`comken/run.py` の `example_libs.v0000` と同じ扱い）。
> 書き換えるのは各ファイルのクラス名・`CREDENTIAL_PREFIX`・`CONFIG_SECTION` の3つ。
> **実名をこのリポジトリへ書き戻さないこと。**
"""

from ..client import Salesforce
from .site_a import SiteA
from .site_b import SiteB
from .site_c import SiteC

# まとめて回すときに使う。組織が増えたらここに足す
SITES: tuple[type[Salesforce], ...] = (SiteA, SiteB, SiteC)

__all__ = ["SiteA", "SiteB", "SiteC", "SITES"]
