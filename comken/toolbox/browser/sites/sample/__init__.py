"""comken/toolbox/browser/sites/sample/__init__.py — サンプルサイト。

``SampleSite`` (と ``SampleBrowserOptions``) をパッケージレベルで公開する。
利用側は ``from comken.toolbox.browser.sites.sample import SampleSite`` で
直接取り出せる (``.site`` の中まで降りなくて良い)。

``SampleSite`` の本体は ``site.py`` に置く (``〇〇Site`` と ``〇〇SiteOptions``
は必ず同じファイル)。
"""

from comken.toolbox.browser.sites.sample.site import (
    SampleBrowserOptions,
    SampleSite,
)

__all__ = ["SampleBrowserOptions", "SampleSite"]
