"""comken/toolbox/browser/sites/ntt/east.py — NTT東（NTTEast） サイト

※ URL はダミー。配置するときに実際の値へ書き換える（詳細は sites/__init__.py）。

このサイトでしか通じないもの（固有の画面遷移・独自の手順）をここに置く。
共通の操作は ``NTTSiteBase`` 側にあるので書かない。
"""

from comken.toolbox.browser.sites.ntt.base import NTTSiteBase


class NTTEast(NTTSiteBase):
    """NTT東のサイトクラス。

    使い方:
        with NTTEast() as ntt:
            secure = ntt.go_login().login(USER, PW)
    """

    NAME = "ntt_east"
    # TODO: 配置するときに実際の URL へ書き換える
    BASE_URL = "https://ntt-higashi.example.co.jp"
