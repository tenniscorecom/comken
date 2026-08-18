"""
src/sites/example/site.py — このプロジェクトのサイトクラス（書き換え前提のサンプル）

1サイト＝1フォルダ（sites/example/）。このサイトに関するものは全部この中に入れる。
サイトを増やすときは sites/<サイト名>/ を隣にもう1つ作るだけで、
既にあるサイトのファイルには触らない（書き方の正本は docs/browser.md）。

NAME / BASE_URL / OPTIONS / OWNER を必ず決める（NAME が空だと起動時にエラー）。

**これは書き換える前提のサンプル**。クラス名・NAME・BASE_URL を自分のサイトに
変えること（変えないまま動かすと example.co.jp へ行くだけで、エラーにはならない）。

`go_〇〇()` が「このサイトで行ける画面」の遷移図になる。呼ぶ側からは
`site.go_login().login("user", "pass")` のように繋げて書ける
（書き方の正本は docs/browser.md「まず動かす」）。

`selenium` を使うので、有効にするなら `requirements.txt` の `# selenium` の
コメントを外すこと（既定ではコメントのまま — 多くのプロジェクトはブラウザを使わない）。

ブラウザ設定（``ExampleSiteOptions``）は **config.ini ではなくこのファイル（サイト側の
Python）に書く**。「環境で変わる非機密の値」ではなく「コードの一部」として扱うため。
設定できる項目とその値は ``print(ExampleSiteOptions())`` で一覧できる。
**ブラウザ操作を使わないプロジェクトでは、``src/sites/`` フォルダごと削除してよい**
（フォルダ1つを消すほうが、site.py・pages/ を1つずつ消すより確実）。
"""

from comken.toolbox.browser import BrowserOptions, SiteBase

from src.sites.example.pages.login_page import LoginPage


class ExampleSiteOptions(BrowserOptions):
    """サイトごとに1クラス作り、変えたい項目だけ上書きする。

    設定できる項目とその値は print(ExampleSiteOptions()) で一覧できる。
    """

    # HEADLESS = True                       # 画面を出さずに動かす
    # DOWNLOAD_DIR = r"C:\作業\downloads"    # サイト名のサブフォルダへ自動で分かれる
    #
    # 標準のフォルダへ入れるなら Paths を使う（OneDrive で場所が移されていても
    # 実際の場所に付いていける）。from comken.toolbox.windows import Paths
    # DOWNLOAD_DIR = Paths.downloads()       # ほかに desktop() / temp_dir()
    # WAIT_SECONDS = 20                      # 要素待機のタイムアウト秒

    # 指定するとログイン状態が次回も残る（サイトごとに別フォルダへ自動で分かれる）
    # PROFILE_ROOT = r"C:\作業\browser_profiles"


class ExampleSite(SiteBase):
    """このシステムが扱うサイトの SiteBase（書き換え前提のサンプル）。"""

    NAME = "example"
    BASE_URL = "https://example.co.jp"
    OPTIONS = ExampleSiteOptions
    OWNER = "プロジェクト名 / 担当者"

    def go_login(self) -> LoginPage:
        """ログイン画面を開く。

        `go_〇〇()` があるものだけが遷移先になるため、コード自体がサイト内の
        遷移図になる。ログイン画面を増やしたくなったら、ここに `go_〇〇()` を
        足していく（例: `go_top()`, `go_admin()` ...）。
        """
        return self.to(LoginPage).go("/login")
