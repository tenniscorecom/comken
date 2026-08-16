"""
src/site.py — このプロジェクトで扱うサイトの SiteBase サブクラスをまとめる

1サイトにつき1クラス。Browsers.launch(SiteBase) に渡す。
NAME / BASE_URL / OPTIONS を必ず決める（NAME が空だと起動時にエラー）。
"""

from comken.toolbox.browser import SiteBase

from .browser_options import KintaiOptions


class Kintai(SiteBase):
    """このシステムが扱う勤怠サイトの SiteBase。"""

    NAME = "kintai"
    BASE_URL = "https://kintai.example.co.jp"
    OPTIONS = KintaiOptions
    OWNER = "プロジェクト名 / 担当者"
