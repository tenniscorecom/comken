"""comken/toolbox/browser/sites/table_site/__init__.py — テーブル表示中心の雛形サイト。

`TableSite` (と `TableBrowserOptions`) をパッケージレベルで公開する。
利用側は ``from comken.toolbox.browser.sites.table_site import TableSite`` で
直接取り出せる (``.site`` の中まで降りなくて良い)。

`TableSite` の本体は ``site.py`` に置く (``〇〇Site`` と ``〇〇SiteOptions``
は必ず同じファイル)。
"""

from comken.toolbox.browser.sites.table_site.site import (
    TableBrowserOptions,
    TableSite,
)

__all__ = ["TableBrowserOptions", "TableSite"]
