"""comken/toolbox/browser/sites/ouju_site/__init__.py — 応需システム用のサイト雛形。

``OujuSite`` (と ``OujuBrowserOptions``) をパッケージレベルで公開する。
利用側は ``from comken.toolbox.browser.sites.ouju_site import OujuSite`` で
直接取り出せる (``.site`` の中まで降りなくて良い)。

``OujuSite`` の本体は ``site.py`` に置く (``〇〇Site`` と ``〇〇SiteOptions``
は必ず同じファイル)。
"""

from comken.toolbox.browser.sites.ouju_site.site import (
    OujuBrowserOptions,
    OujuSite,
)

__all__ = ["OujuBrowserOptions", "OujuSite"]
