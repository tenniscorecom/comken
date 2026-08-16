"""
sample_site.py — サンプルサイトの SiteBase クラス。

1サイトにつき1クラスを作って、固有の値をそこに集める。
Browsers.launch(SiteBase) で起動し、戻り値から .session に繋がる。
"""

from comken.toolbox.browser import SiteBase

from .browser_options import SampleBrowserOptions


class SampleSite(SiteBase):
    """the-internet.herokuapp.com 用の SiteBase。"""

    NAME = "sample"
    BASE_URL = "https://the-internet.herokuapp.com"
    OPTIONS = SampleBrowserOptions
    OWNER = "sample_login / サンプル"
