"""ブラウザ操作（Edge / selenium）。

サイトが1つでも複数でも、書き方は同じ:

    from comken.browser import Browsers

    with Browsers() as browsers:
        kintai = browsers.launch("kintai", KintaiOptions)
        data = KintaiFlow(kintai).fetch()

サイトを増やすときは launch を1行足す。同時に走らせたくなったら parallel で包む。
詳しくは docs/ブラウザ操作.md を参照。

    Browsers        複数サイトのブラウザをまとめて起動・終了する（入口）
    BrowserSession  1サイト分のブラウザ。Browsers.launch() が返す
    BrowserOptions  起動オプション。サイトごとにサブクラスを作って上書きする
    Page / SitePage 1画面ぶんの操作をまとめる基底クラス
    Locator         セレクター（Locator.id(...) / .css(...) など）
    DownloadDir     ダウンロード先フォルダ。完了待ちに使う
    BackgroundTask  Browsers.start() が返す取っ手。wait() で結果を受け取る
"""

from .download import DownloadDir
from .fleet import Browsers
from .locator import Locator
from .options import BrowserOptions
from .page import Page, SitePage
from .session import BrowserSession
from .task import BackgroundTask

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
