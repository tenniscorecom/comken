"""
src/sites/example/site.py — このプロジェクトのサイトクラス（書き換え前提のサンプル）

1サイト＝1フォルダ（sites/example/）。このサイトに関するものは全部この中に入れる。
サイトを増やすときは sites/<サイト名>/ を隣にもう1つ作るだけで、
既にあるサイトのファイルには触らない（書き方の正本は docs/browser.md）。

NAME / BASE_URL / OWNER を必ず決める（NAME が空だと起動時にエラー）。

**これは書き換える前提のサンプル**。クラス名・NAME・BASE_URL を自分のサイトに
変えること（変えないまま動かすと example.co.jp へ行くだけで、エラーにはならない）。

`go_〇〇()` が「このサイトで行ける画面」の遷移図になる。呼ぶ側からは
`site.go_login().login("user", "pass")` のように繋げて書ける
（書き方の正本は docs/browser.md「まず動かす」）。

`selenium` を使うので、有効にするなら `requirements.txt` の `# selenium` の
コメントを外すこと（既定ではコメントのまま — 多くのプロジェクトはブラウザを使わない）。

BrowserOptions（ヘッドレス・ダウンロード先・待ち時間・ログイン状態の保持など）は
**既定のままでよければ OPTIONS 行を書く必要はない**。変えたいときだけ、
``BrowserOptions`` のサブクラスをこのファイルに作って ``OPTIONS = 〇〇`` を
書く（設定できる項目は ``print(BrowserOptions())`` で一覧できる）。
詳しい手順は docs/browser.md「新しい社内システムを追加する手順」を参照。

**ブラウザ操作を使わないプロジェクトでは、``src/sites/`` フォルダごと削除してよい**
（フォルダ1つを消すほうが、site.py・pages/ を1つずつ消すより確実）。
"""

from comken.toolbox.browser import SiteBase

from src.sites.example.pages.login_page import LoginPage


class ExampleSite(SiteBase):
    """このシステムが扱うサイトの SiteBase（書き換え前提のサンプル）。"""

    NAME = "example"
    BASE_URL = "https://example.co.jp"
    OWNER = "プロジェクト名 / 担当者"

    def go_login(self) -> LoginPage:
        """ログイン画面を開く。

        `go_〇〇()` があるものだけが遷移先になるため、コード自体がサイト内の
        遷移図になる。ログイン画面を増やしたくなったら、ここに `go_〇〇()` を
        足していく（例: `go_top()`, `go_admin()` ...）。
        """
        return self.to(LoginPage).go("/login")
