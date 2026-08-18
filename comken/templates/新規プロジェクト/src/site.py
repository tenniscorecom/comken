"""
src/site.py — このプロジェクトで扱うサイトの SiteBase サブクラスをまとめる

1サイトにつき1クラス。Browsers.launch(SiteBase) に渡す。
NAME / BASE_URL / OPTIONS を必ず決める（NAME が空だと起動時にエラー）。

**これは書き換える前提のサンプル**。クラス名・NAME・BASE_URL を自分のサイトに
変えること（変えないまま動かすと example.co.jp へ行くだけで、エラーにはならない）。

行ける画面は `go_〇〇()` で書く（書き方の正本は docs/browser.md）。
`go_〇〇()` があるものだけが遷移先になるため、コード自体がサイト内の遷移図になる。

**ブラウザ操作を使わないプロジェクトでは、このファイルは削除してよい。**

`selenium` を使うので、有効にするなら `requirements.txt` の `# selenium` の
コメントを外すこと（既定ではコメントのまま — 多くのプロジェクトはブラウザを使わない）。
"""

from comken.toolbox.browser import SiteBase

from src.browser_options import ExampleSiteOptions


class ExampleSite(SiteBase):
    """このシステムが扱うサイトの SiteBase（書き換え前提のサンプル）。"""

    NAME = "example"
    BASE_URL = "https://example.co.jp"
    OPTIONS = ExampleSiteOptions
    OWNER = "プロジェクト名 / 担当者"

    # 例: 行ける画面は go_〇〇() でメソッドを書く
    # def go_login(self) -> LoginPage:
    #     """ログイン画面を開く。"""
    #     return self.to(LoginPage).go("/login")
