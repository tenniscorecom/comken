"""comken/toolbox/browser/sites/ams/site.py — AMS 用の SiteBase クラス。

このサイトのものは sites/ams/ の中で完結する（site.py・pages/）。
サイトを増やすときは sites/<サイト名>/ をもう1つ作る。

1サイトにつき ``AMS`` と ``AMSBrowserOptions`` を **同じ ``site.py`` に置く**
（``〇〇Site`` と ``〇〇SiteOptions`` は必ずセットで、フォルダが同じならファイルも
分ける理由が無い）。ブラウザ設定は config.ini ではなくこのファイル（サイト側の
Python）に書き、設定できる項目は ``print(AMSBrowserOptions())`` で一覧できる。

1サイト＝1フォルダで、起動オプション・ダウンロード先・ログイン状態はサイトごとに独立する
（片方の設定がもう片方へ影響しない）。

行ける画面は `go_〇〇()` で書き、コードがそのまま遷移図になるようにする
（書き方の正本は docs/browser.md）。

> [!note] 雛形の値
> BASE_URL は HTTPS 非対応・IP アドレス直打ちの社内システムを想定したダミー値
> （203.0.113.10 は RFC 5737 の例示用アドレス、実在しない）。セレクタも
> example の値のまま。利用プロジェクト側で実際の値へ書き換える前提。
"""

# 遷移先の import を型注釈だけ TYPE_CHECKING、実行時はメソッド内に分けているのは、
# 画面クラス同士の循環importを避けるため（循環の有無に関わらず一律この形にする）
from __future__ import annotations

from typing import TYPE_CHECKING

from comken.toolbox.browser import BrowserOptions, SiteBase

if TYPE_CHECKING:
    from comken.toolbox.browser.sites.ams.pages.customer_list_page import CustomerListPage
    from comken.toolbox.browser.sites.ams.pages.login_page import LoginPage


class AMSBrowserOptions(BrowserOptions):
    """ams 用のブラウザオプション。

    デフォルト（BrowserOptions）から変更したいものだけ上書きする。
    全オプションのデフォルト値は comken/toolbox/browser/options.py を参照。
    """

    DRIVER_PATH = r"C:\Users\Public\Documents\msedgedriver.exe"

    # このサンプルではシークレットモードを使わない
    INCOGNITO = False

    # ウィンドウサイズを固定（--start-maximized と併用不可なので無効化）
    START_MAXIMIZED = False
    WINDOW_SIZE = "1600,1024"

    # 装置画面を開く際、既定の10秒だとタイムアウトすることがあったため延長
    WAIT_SECONDS = 30


class AMS(SiteBase):
    """ams 雛形用の SiteBase。

    URL や要素セレクタは example の値のまま。利用プロジェクト側で継承して書き換える。
    """

    NAME = "ams"
    BASE_URL = "http://203.0.113.10"
    OPTIONS = AMSBrowserOptions
    OWNER = "comken"

    def go_login(self) -> LoginPage:
        """ログイン画面を開く。"""
        from comken.toolbox.browser.sites.ams.pages.login_page import LoginPage

        return self.to(LoginPage).go("/login")

    def go_customer_list(self) -> CustomerListPage:
        """お客様一覧画面を開く（ログイン後、URL 直飛びで行ける）。"""
        from comken.toolbox.browser.sites.ams.pages.customer_list_page import CustomerListPage

        return self.to(CustomerListPage).go("/customers")
