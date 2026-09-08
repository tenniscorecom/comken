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
> URL・オプションの値は ``ouju`` と同じダミーのまま。利用プロジェクト側で
> 実際の値へ書き換える前提（実際のセレクタや画面遷移は利用者が後で埋める）。
"""

from comken.toolbox.browser import BrowserOptions, SiteBase
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


class AMS(SiteBase):
    """ams 雛形用の SiteBase。

    URL や要素セレクタは example の値のまま。利用プロジェクト側で継承して書き換える。
    """

    NAME = "ams"
    BASE_URL = "https://example.com"
    OPTIONS = AMSBrowserOptions
    OWNER = "comken"

    def go_login(self) -> LoginPage:
        """ログイン画面を開く。"""
        return self.to(LoginPage).go("/login")
