"""
src/site.py — このプロジェクトで扱うサイトの Site サブクラスをまとめる

1サイトにつき1クラス。Browsers.launch(Site) に渡す。
NAME / BASE_URL / OPTIONS を必ず決める（NAME が空だと起動時にエラー）。
"""

from comken.toolbox.browser import Site

from .browser_options import KintaiOptions


class Kintai(Site):
    """このシステムが扱う勤怠サイトの Site。"""

    NAME = "kintai"
    BASE_URL = "https://kintai.example.co.jp"
    OPTIONS = KintaiOptions
