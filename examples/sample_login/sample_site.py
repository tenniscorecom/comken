"""
sample_site.py — サンプルサイトの Site クラス。

1サイトにつき1クラスを作って、固有の値をそこに集める。
Browsers.launch(Site) で起動し、戻り値から .session に繋がる。
"""

from comken.toolbox.browser import Site

from .browser_options import SampleBrowserOptions


class SampleSite(Site):
    """the-internet.herokuapp.com 用の Site。"""

    NAME = "sample"
    BASE_URL = "https://the-internet.herokuapp.com"
    OPTIONS = SampleBrowserOptions
