"""
sample_site.py — サンプルサイトの SiteBase クラス。

1サイトにつき1クラスを作って、固有の値をそこに集める。
行ける画面は `go_〇〇()` で書き、コードがそのまま遷移図になるようにする
（書き方の正本は docs/browser.md）。
"""

from comken.toolbox.browser import SiteBase

from .browser_options import SampleBrowserOptions
from .pages.login_page import LoginPage


class SampleSite(SiteBase):
    """the-internet.herokuapp.com 用の SiteBase。"""

    NAME = "sample"
    BASE_URL = "https://the-internet.herokuapp.com"
    OPTIONS = SampleBrowserOptions
    OWNER = "sample_login / サンプル"

    def go_login(self) -> LoginPage:
        """ログイン画面を開く。"""
        return self.to(LoginPage).go("/login")
