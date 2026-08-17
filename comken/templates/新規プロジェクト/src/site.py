"""
src/site.py — このプロジェクトで扱うサイトの SiteBase サブクラスをまとめる

1サイトにつき1クラス。Browsers.launch(SiteBase) に渡す。
NAME / BASE_URL / OPTIONS を必ず決める（NAME が空だと起動時にエラー）。

行ける画面は `go_〇〇()` で書く（書き方の正本は docs/browser.md）。
`go_〇〇()` があるものだけが遷移先になるため、コード自体がサイト内の遷移図になる。
"""

from comken.toolbox.browser import SiteBase

# 画面クラスを増やすたびに、ここに from .pages.kintai.<画面> import <画面> を足す
from .browser_options import KintaiOptions


class Kintai(SiteBase):
    """このシステムが扱う勤怠サイトの SiteBase。"""

    NAME = "kintai"
    BASE_URL = "https://kintai.example.co.jp"
    OPTIONS = KintaiOptions
    OWNER = "プロジェクト名 / 担当者"

    # 例: 行ける画面は go_〇〇() でメソッドを書く
    # def go_login(self) -> LoginPage:
    #     """ログイン画面を開く。"""
    #     return self.to(LoginPage).go("/login")
