"""comken/toolbox/browser/sites/cms/__init__.py — CMS 用のサイト雛形。

``CMS`` (と ``CMSBrowserOptions``) をパッケージレベルで公開する。
利用側は ``from comken.toolbox.browser.sites.cms import CMS`` で
直接取り出せる (``.site`` の中まで降りなくて良い)。

``CMS`` の本体は ``site.py`` に置く (``〇〇Site`` と ``〇〇SiteOptions``
は必ず同じファイル)。
"""

from comken.toolbox.browser.sites.cms.site import (
    CMS,
    CMSBrowserOptions,
)

__all__ = ["CMSBrowserOptions", "CMS"]
