"""comken/toolbox/browser/page/__init__.py — 画面クラス（Page Object）用の内部パッケージ。

読む順番:

1. base.py       — 共有状態（session）と内部ヘルパー（_until / _visible）
2. navigation.py  — open() / save_screenshot()
3. operations.py   — click() / input() / select_*() / drag_drop() / scroll_*()
4. reading.py       — read_*() / has_element() / count_elements()
5. waiting.py        — wait_visible() / wait_invisible()
6. alerts.py          — alert_*()
7. escape.py           — frame() / find_element*() / execute_script()
8. model.py             — 上記すべてを束ねた Page 本体
9. site.py               — SitePage（サイト共通の画面クラス）

利用側はこの内部構造へ依存せず、from comken.toolbox.browser import ... を使う。
"""

from comken.toolbox.browser.page.model import Page
from comken.toolbox.browser.page.site import SitePage

__all__ = ["Page", "SitePage"]
