"""comken/toolbox/salesforce/sites/__init__.py — 組織（サイト）ごとの Salesforce クライアント。

組織は My Domain の URL と認証情報が違うので、1組織につき1クラス・1インスタンスにする。
共通の操作（SOQL・CRUD・レポート・計測）は `SalesforceBase` が持っているので、
ここに書くのは**その組織でしか通じないもの**だけにする。

    from comken.toolbox.salesforce.sites import Sandbox

    with Sandbox() as sf:
        rows = sf.案件一覧()

URL と認証情報のシステム名はクラス定数なので、呼び出し側は何も渡さなくてよい。
本番とテストで登録を切り替えるときだけシステム名を渡す:

    with Sandbox(prefix=config.SALESFORCE.CREDENTIAL_PREFIX) as sf:
        ...

client_id / client_secret は DPAPI から読む（`comken.toolbox.credentials`）ので、
コードにも config.ini にも秘密の値は現れない。

組織を増やすときは、このフォルダにファイルを1つ足して `SalesforceBase` を継承する。

> [!warning] 組織名と URL は仮の値
> **このリポジトリは公開しているので、実際の組織名・URL を書かない。**
> `Sandbox` の `DOMAIN_URL` はダミーで、共有サーバーへ配置するときに
> 実際の値へ書き換える（`comken/run.py` の `example_libs.v0000` と同じ扱い）。
> 書き換えるのは各ファイルの `DOMAIN_URL`・`CREDENTIAL_PREFIX`・`REPORT_*` と、
> 組織名を出すならクラス名。**実名をこのリポジトリへ書き戻さないこと。**
"""

from urllib.parse import urlsplit

from ....exceptions import SalesforceSiteNotFoundError
from ..client import SalesforceBase
from .sandbox import Sandbox

# 登録済みの組織。URL からどの組織へつなぐかを引くのに使う。
# **組織を増やしたらここにも足す。** 足し忘れると、その組織の URL だけが
# SalesforceSiteNotFoundError になる（黙って別組織へつなぐことはない）
SITES: tuple[type[SalesforceBase], ...] = (Sandbox,)

__all__ = ["SITES", "Sandbox", "site_for"]


def site_for(url: str) -> type[SalesforceBase]:
    """レポートの URL から、つなぐ組織のクラスを返す。

    レポートの一覧表には**複数の組織の URL が混ざる**。どの組織のレポートかは
    URL のドメイン（My Domain）で決まるので、表に行を足すだけで新しい組織の
    レポートも取れるようにする。組織を人が選ぶ列を作ると、URL と食い違ったときに
    別組織へ問い合わせて「レポートが見つからない」という分かりにくい失敗になる。

        site_for("https://example--sandbox.sandbox.my.salesforce.com/lightning/...")
        # → Sandbox

    Args:
        url: レポートを開いたときのアドレス。**ドメインを含む URL であること**
            （レポート ID だけでは、どの組織のものか決められない）。

    Raises:
        SalesforceSiteNotFoundError: 登録済みのどの組織にも当てはまらない場合。
    """
    host = _host_of(url)
    for site in SITES:
        if host and _host_of(site.DOMAIN_URL) == host:
            return site
    raise SalesforceSiteNotFoundError(url, [site.DOMAIN_URL for site in SITES])


def _host_of(url: str) -> str:
    """URL からホスト名だけを取り出す（大文字小文字の違いは無視する）。"""
    return urlsplit(url.strip()).netloc.lower()
