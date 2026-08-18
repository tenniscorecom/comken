"""comken/toolbox/browser/sites/sample/pages/app_page.py — このサンプルサイト共通の SitePage

【使い方ガイド】
---------------------------------------------------------------------------
プロジェクトでは必ずこのような「サイト共通ベースクラス」を1つ作る。
  - BASE_URL: サイトのルート URL を書く
  - サイト全体で共通の操作（ヘッダーメニュー、ログアウト等）をここに書く
  - 各画面クラス（LoginPage, DashboardPage 等）はこのクラスを継承する

継承の構造（コピーして使う）:
    Page       ← comken が提供（click / input / select / alert 等の操作）
      └── SitePage   ← comken が提供（BASE_URL / go() を追加）
            └── AppPage   ← このファイル（サイト共通処理を追加）
                  └── LoginPage / SecurePage / ...   ← 各画面
---------------------------------------------------------------------------

【画面遷移の書き方】
---------------------------------------------------------------------------
「次の画面に移動するメソッド」は、遷移先のページクラスを返すことで
  どの画面に移ったかをコードで追えるようにする。
  画面インスタンスを新しく作るときは `self.to(遷移先クラス)` を使う
  （書き方の正本は docs/browser.md）:

    class LoginPage(AppPage):
        USERNAME = Locator.id("username")     # セレクターはクラス上部にまとめる
        PASSWORD = Locator.id("password")
        LOGIN_BTN = Locator.id("login-btn")

        def login(self, username, password) -> "SecurePage":   # 戻り値の型を書く
            self.input(self.USERNAME, username)
            self.input(self.PASSWORD, password)
            self.click(self.LOGIN_BTN)
            return self.to(SecurePage)        # 遷移先クラスを返す

    # 呼び出し側
    login_page = sample.go_login()           # サイトクラスの go_〇〇() から始める
    secure_page = login_page.login("user", "pass")   # SecurePage が返ってくる
    print(secure_page.get_heading())                 # そのまま次の画面の操作が書ける
---------------------------------------------------------------------------
"""

from comken.toolbox.browser import Locator, SitePage


class AppPage(SitePage):
    """このサンプルサイト（the-internet.herokuapp.com）共通の基底クラス。

    全画面クラスはこのクラスを継承する。
    サイト固有の共通処理（ヘッダー操作・共通エラーメッセージ取得等）をここに書く。
    """

    BASE_URL = "https://the-internet.herokuapp.com"

    FLASH_MESSAGE = Locator.css("#flash")

    def get_flash_message(self) -> str:
        """ページ上部に表示されるフラッシュメッセージを取得する。
        ログイン成功・失敗の通知など、サイト全体で共通の要素。
        """
        return self.read_text(self.FLASH_MESSAGE)
