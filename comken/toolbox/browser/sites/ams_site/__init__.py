"""comken/toolbox/browser/sites/ams_site/__init__.py — AMS 用のサイト雛形。

``AMSSite`` (と ``AMSBrowserOptions``) をパッケージレベルで公開する。
利用側は ``from comken.toolbox.browser.sites.ams_site import AMSSite`` で
直接取り出せる (``.site`` の中まで降りなくて良い)。

``AMSSite`` の本体は ``site.py`` に置く (``〇〇Site`` と ``〇〇SiteOptions``
は必ず同じファイル)。
"""

from comken.toolbox.browser.sites.ams_site.site import (
    AMSBrowserOptions,
    AMSSite,
)

__all__ = ["AMSBrowserOptions", "AMSSite"]
