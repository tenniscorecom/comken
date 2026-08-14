"""comken/browser/management/__init__.py — ブラウザー管理用の内部パッケージ。

読む順番:

1. ``browsers.py`` — 複数ブラウザーをまとめる公開入口
2. ``sessions.py`` — 1サイト分のWebDriverと排他制御
3. ``startup.py`` — Edgeの起動・初期化・ドライバー更新
4. ``tasks.py`` — 裏で動かした処理の結果管理
5. ``tabs.py`` — 1セッション内のタブ開閉

利用側はこの内部構造へ依存せず、``from comken.browser import ...`` を使う。
"""

from __future__ import annotations

from .browsers import Browsers as Browsers
from .sessions import BrowserSession as BrowserSession
from .tasks import BackgroundTask as BackgroundTask
