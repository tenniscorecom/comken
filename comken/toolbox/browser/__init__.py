"""comken/toolbox/browser/__init__.py — ブラウザ操作（Edge / selenium）。

サイトが1つでも複数でも、書き方は同じ:

    from comken.toolbox.browser import Browsers

    with Browsers() as browsers:
        kintai = browsers.launch(Kintai)
        data = KintaiFlow(kintai.session).fetch()

サイトを増やすときは launch を1行足す。同時に走らせたくなったら parallel で包む。
詳しくは docs/browser.md を参照。

    Browsers        複数サイトのブラウザをまとめて起動・終了する（入口）
    BrowserSession  1サイト分のブラウザ。launch(SiteBase) では SiteBase.session 経由で扱う
    SiteBase            1サイトの入口。Browsers.launch() に渡す土台クラス
    BrowserOptions  起動オプション。サイトごとにサブクラスを作って上書きする
    Page / SitePage 1画面ぶんの操作をまとめる基底クラス
    Locator         セレクター（Locator.id(...) / .css(...) など）
    DownloadDir     ダウンロード先フォルダ。完了待ちに使う
    BackgroundTask  Browsers.run_task() が返す取っ手。wait() で結果を受け取る
"""

from comken.toolbox.browser.download import DownloadDir
from comken.toolbox.browser.locator import Locator
from comken.toolbox.browser.management import BackgroundTask, Browsers, BrowserSession
from comken.toolbox.browser.options import BrowserOptions
from comken.toolbox.browser.page import Page, SitePage
from comken.toolbox.browser.sitebase import SiteBase

__all__ = [
    "Browsers",
    "BrowserSession",
    "SiteBase",
    "BrowserOptions",
    "Page",
    "SitePage",
    "Locator",
    "DownloadDir",
    "BackgroundTask",
]
