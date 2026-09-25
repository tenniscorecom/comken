"""comken/toolbox/browser/sites/ouju/__init__.py — 応需システム用のサイト雛形。

``Ouju`` (と ``OujuBrowserOptions``) をパッケージレベルで公開する。
利用側は ``from comken.toolbox.browser.sites.ouju import Ouju`` で
直接取り出せる (``.site`` の中まで降りなくて良い)。

``Ouju`` の本体は ``site.py`` に置く (``〇〇Site`` と ``〇〇SiteOptions``
は必ず同じファイル)。
"""

from comken.toolbox.browser.sites.ouju.site import (
    Ouju,
    OujuBrowserOptions,
)

__all__ = ["OujuBrowserOptions", "Ouju"]
