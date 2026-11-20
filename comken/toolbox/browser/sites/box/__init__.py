"""comken/toolbox/browser/sites/box/__init__.py — Box 用のサイト。

``Box`` (と ``BoxBrowserOptions``) をパッケージレベルで公開する。
利用側は ``from comken.toolbox.browser.sites.box import Box`` で
直接取り出せる (``.site`` の中まで降りなくて良い)。

``Box`` の本体は ``site.py`` に置く (``〇〇Site`` と ``〇〇SiteOptions``
は必ず同じファイル)。

    from comken.toolbox.browser.sites.box import Box

    with Box() as box:
        box.login()
        folder = box.go_folder("0")
        for item in folder.items():
            print(item.name)
"""

from comken.toolbox.browser.sites.box.site import (
    Box,
    BoxBrowserOptions,
)

__all__ = ["BoxBrowserOptions", "Box"]
