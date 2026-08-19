"""comken/toolbox/browser/sites/login_site/__init__.py — ログインフォーム中心の雛形サイト。

``LoginSite`` (と ``LoginBrowserOptions``) をパッケージレベルで公開する。
利用側は ``from comken.toolbox.browser.sites.login_site import LoginSite`` で
直接取り出せる (``.site`` の中まで降りなくて良い)。

``LoginSite`` の本体は ``site.py`` に置く (``〇〇Site`` と ``〇〇SiteOptions``
は必ず同じファイル)。
"""

from comken.toolbox.browser.sites.login_site.site import (
    LoginBrowserOptions,
    LoginSite,
)

__all__ = ["LoginBrowserOptions", "LoginSite"]
