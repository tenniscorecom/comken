"""comken/toolbox/browser/sites/ntt/__init__.py — NTT西/NTT東 サイト。

``NTTNishi`` / ``NTTHigashi`` をパッケージレベルで公開する。
利用側は ``from comken.toolbox.browser.sites.ntt import NTTNishi`` で
直接取り出せる（``.nishi`` の中まで降りなくて良い）。

**このフォルダだけ、docs/browser.md の「1サイト＝1フォルダで完結」を意図的に破る。**
理由・トレードオフは ``base.py`` の docstring を参照。
"""

from comken.toolbox.browser.sites.ntt.base import NTTBrowserOptions, NTTSiteBase
from comken.toolbox.browser.sites.ntt.higashi import NTTHigashi
from comken.toolbox.browser.sites.ntt.nishi import NTTNishi

__all__ = ["NTTBrowserOptions", "NTTSiteBase", "NTTNishi", "NTTHigashi"]
