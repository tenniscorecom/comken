"""comken/toolbox/salesforce/hosts.py — URL のホスト名を、組織を見分ける形にそろえる。

レポートの URL は、ブラウザのアドレスバーから貼ると Lightning の画面のホスト名
（``○○.lightning.force.com``）になることがある。組織クラスの ``DOMAIN_URL`` は My Domain
（``○○.my.salesforce.com``）で書くので、そのままでは同じ組織なのにホスト名が一致しない。
ここで Lightning 側の末尾を My Domain 側にそろえて、組織を見分けるのに使う。

    host_of("https://example.lightning.force.com/lightning/r/Report/00O.../view")
    # → "example.my.salesforce.com"

サンドボックスも同じ規則（``○○--△△.sandbox.lightning.force.com`` →
``○○--△△.sandbox.my.salesforce.com``）。API・ブラウザの両方の ``site_for`` が使う。
"""

from __future__ import annotations

from urllib.parse import urlsplit

_LIGHTNING_SUFFIX = ".lightning.force.com"
_MY_DOMAIN_SUFFIX = ".my.salesforce.com"


def host_of(url: str) -> str:
    """URL から組織を見分けるホスト名を取り出す（小文字。Lightning は My Domain に読み替える）。"""
    host = urlsplit(url.strip()).netloc.lower()
    if host.endswith(_LIGHTNING_SUFFIX):
        return host[: -len(_LIGHTNING_SUFFIX)] + _MY_DOMAIN_SUFFIX
    return host
