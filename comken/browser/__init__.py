"""comken/browser/__init__.py — ブラウザ操作（Edge / selenium）。

サイトが1つでも複数でも、書き方は同じ:

    from comken.browser import Browsers

    with Browsers() as browsers:
        kintai = browsers.launch("kintai", KintaiOptions)
        data = KintaiFlow(kintai).fetch()

サイトを増やすときは launch を1行足す。同時に走らせたくなったら parallel で包む。
詳しくは docs/browser.md を参照。

    Browsers        複数サイトのブラウザをまとめて起動・終了する（入口）
    BrowserSession  1サイト分のブラウザ。Browsers.launch() が返す
    BrowserOptions  起動オプション。サイトごとにサブクラスを作って上書きする
    Page / SitePage 1画面ぶんの操作をまとめる基底クラス
    Locator         セレクター（Locator.id(...) / .css(...) など）
    DownloadDir     ダウンロード先フォルダ。完了待ちに使う
    BackgroundTask  Browsers.run_task() が返す取っ手。wait() で結果を受け取る
"""

from __future__ import annotations

from .download import DownloadDir
from .locator import Locator
from .management import BackgroundTask, Browsers, BrowserSession
from .options import BrowserOptions
from .page import Page, SitePage

__all__ = [
    "Browsers",
    "BrowserSession",
    "BrowserOptions",
    "Page",
    "SitePage",
    "Locator",
    "DownloadDir",
    "BackgroundTask",
]

# 2026-08-03 の作り直しで無くなった名前と、その置き換え先。
# 素の ImportError は「cannot import name 'EdgeDriver'」としか出ず、
# 何に書き換えればよいか分からないため、案内を添えて送出する
_REMOVED_NAMES = {
    "EdgeDriver": (
        "Browsers に変わりました。1サイトでも複数サイトでも同じ書き方になります。\n"
        "  with Browsers() as browsers:\n"
        '      kintai = browsers.launch("kintai", KintaiOptions)\n'
        "      kintai.open(...)"
    ),
    "BasePage": (
        "Page に変わりました。セレクターは Locator にまとめ、\n"
        "click_id / input_css のような種別付きメソッドは\n"
        "click(LOC) / input(LOC, text) に一本化されています。"
    ),
}


def __getattr__(name: str) -> object:
    """無くなった名前が使われたときに、書き換え先を伝える。"""
    if name in _REMOVED_NAMES:
        raise AttributeError(
            f"comken.browser.{name} は廃止されました。\n"
            f"{_REMOVED_NAMES[name]}\n"
            "書き換え方は docs/browser.md を参照してください。"
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
