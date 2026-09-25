"""comken/toolbox/browser/management/__init__.py — ブラウザー管理用の内部パッケージ。

読む順番:

1. ``sessions.py`` — 1サイト分の WebDriver
2. ``startup.py`` — Edge の起動・初期化・ドライバー更新
3. ``tabs.py`` — 1セッション内のタブ開閉

利用側はこの内部構造へ依存せず、``from comken.toolbox.browser import ...`` を使う。
"""

from comken.toolbox.browser.management.sessions import BrowserSession

__all__ = ["BrowserSession"]
