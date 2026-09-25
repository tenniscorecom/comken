"""comken/toolbox/browser/__init__.py — ブラウザ操作（Edge / selenium）。

サイトは SiteBase のサブクラスを作って ``with`` で使う。複数サイトは
``with`` を並べればよい:

    from comken.toolbox.browser import SiteBase

    class Kintai(SiteBase):
        NAME = "kintai"
        BASE_URL = "https://kintai.example.co.jp"
        OWNER = "勤怠 / 小栗"

    with Kintai() as kintai:
        kintai.go_login().login("user01", "password")

    # 複数サイトは with を並べるだけ
    with Kintai() as kintai, Keiri() as keiri:
        ...

    # 同じサイトを2アカウントで開くときは name= でセッション名を分ける
    with Kintai(name="kintai_a") as a, Kintai(name="kintai_b") as b:
        ...

詳しくは docs/機能/browser.md を参照。

    BrowserSession  1サイト分のブラウザ。SiteBase.session 経由で扱う
    SiteBase       1サイトの入口。``with`` で直接起動する
    BrowserOptions 起動オプション。サイトごとにサブクラスを作って上書きする
    Page / SitePage 1画面ぶんの操作をまとめる基底クラス
    Locator        セレクター（Locator.id(...) / .css(...) など）
    DownloadDir    ダウンロード先フォルダ。完了待ちに使う
"""

from comken.toolbox.browser.download import DownloadDir
from comken.toolbox.browser.locator import Locator
from comken.toolbox.browser.management import BrowserSession
from comken.toolbox.browser.options import BrowserOptions
from comken.toolbox.browser.page import Page, SitePage
from comken.toolbox.browser.sitebase import SiteBase

__all__ = [
    "BrowserSession",
    "SiteBase",
    "BrowserOptions",
    "Page",
    "SitePage",
    "Locator",
    "DownloadDir",
]
