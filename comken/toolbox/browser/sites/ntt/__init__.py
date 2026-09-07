"""comken/toolbox/browser/sites/ntt/__init__.py — NTT西/NTT東 サイト。

``NTTWest`` / ``NTTEast`` をパッケージレベルで公開する。
利用側は ``from comken.toolbox.browser.sites.ntt import NTTWest`` で
直接取り出せる（``.west`` の中まで降りなくて良い）。

**このフォルダだけ、docs/browser.md の「1サイト＝1フォルダで完結」を意図的に破る。**
理由・トレードオフは ``base.py`` の docstring を参照。
"""

from comken.toolbox.browser.sites.ntt.base import NTTBrowserOptions, NTTSiteBase
from comken.toolbox.browser.sites.ntt.east import NTTEast
from comken.toolbox.browser.sites.ntt.west import NTTWest

__all__ = ["NTTBrowserOptions", "NTTSiteBase", "NTTWest", "NTTEast"]
