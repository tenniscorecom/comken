"""
sites/sample/site.py — サンプルサイトの SiteBase クラス。

このサイトのものは sites/sample/ の中で完結する（site.py・pages/）。
サイトを増やすときは sites/<サイト名>/ をもう1つ作る。

1サイトにつき ``SampleSite`` と ``SampleBrowserOptions`` を **同じ ``site.py`` に置く**
（``〇〇Site`` と ``〇〇SiteOptions`` は必ずセットで、フォルダが同じならファイルも
分ける理由が無い）。ブラウザ設定は config.ini ではなくこのファイル（サイト側の
Python）に書き、設定できる項目は ``print(SampleBrowserOptions())`` で一覧できる。

1サイト＝1フォルダで、起動オプション・ダウンロード先・ログイン状態はサイトごとに独立する
（片方の設定がもう片方へ影響しない）。

行ける画面は `go_〇〇()` で書き、コードがそのまま遷移図になるようにする
（書き方の正本は docs/browser.md）。
"""

from comken.toolbox.browser import BrowserOptions, SiteBase

from .pages.login_page import LoginPage


class SampleBrowserOptions(BrowserOptions):
    """sample_login 用のブラウザオプション。

    デフォルト（BrowserOptions）から変更したいものだけ上書きする。
    全オプションのデフォルト値は comken/toolbox/browser/options.py を参照。
    """

    DRIVER_PATH = r"C:\Users\Public\Documents\msedgedriver.exe"

    # このサンプルではシークレットモードを使わない
    INCOGNITO = False

    # ウィンドウサイズを固定（--start-maximized と併用不可なので無効化）
    START_MAXIMIZED = False
    WINDOW_SIZE = "1600,1024"


class SampleSite(SiteBase):
    """the-internet.herokuapp.com 用の SiteBase。"""

    NAME = "sample"
    BASE_URL = "https://the-internet.herokuapp.com"
    OPTIONS = SampleBrowserOptions
    OWNER = "sample_login / サンプル"

    def go_login(self) -> LoginPage:
        """ログイン画面を開く。"""
        return self.to(LoginPage).go("/login")
