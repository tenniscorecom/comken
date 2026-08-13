"""組織（サイト）ごとの Salesforce クライアント。

組織は My Domain の URL が違うので、1組織につき1クラス・1インスタンスにする。
共通の操作（SOQL・CRUD・レポート・計測）は `Salesforce` が持っているので、
ここに書くのは**その組織でしか通じないもの**だけにする。

    from comken.salesforce.sites import SiteA

    with SiteA.from_credentials(config.SITE_A.DOMAIN_URL) as sf:
        rows = sf.案件一覧()

client_id / client_secret は DPAPI から読む（`comken.credentials`）ので、
コードにも config.ini にも秘密の値は現れない。

3組織をまとめて回すときは SITES を使う:

    from comken.salesforce.sites import SITES

    for site_class in SITES:
        domain_url = getattr(config, site_class.CONFIG_SECTION).DOMAIN_URL
        with site_class.from_credentials(domain_url) as sf:
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
