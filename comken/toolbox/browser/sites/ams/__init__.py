"""comken/toolbox/browser/sites/ams/__init__.py — AMS 用のサイト雛形。

``AMS`` (と ``AMSBrowserOptions``) をパッケージレベルで公開する。
利用側は ``from comken.toolbox.browser.sites.ams import AMS`` で
直接取り出せる (``.site`` の中まで降りなくて良い)。

``AMS`` の本体は ``site.py`` に置く (``〇〇Site`` と ``〇〇SiteOptions``
は必ず同じファイル)。
"""

from comken.toolbox.browser.sites.ams.site import (
    AMS,
    AMSBrowserOptions,
)

__all__ = ["AMSBrowserOptions", "AMS"]
