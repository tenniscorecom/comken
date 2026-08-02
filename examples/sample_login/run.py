"""
サンプル: ログイン → セキュアエリア確認 → ログアウト

実行方法:
    リポジトリのルートで python -m examples.sample_login.run

サイトが1つでも Browsers を使う。サイトが増えたときに書き方を変えなくて済むため
（増やすときは launch を1行足すだけ。複数サイトの例は docs/ブラウザ操作.md を参照）。
"""

from comken.browser import Browsers
from examples.sample_login.browser_options import SampleBrowserOptions
from examples.sample_login.pages.login_page import LoginPage

USERNAME = "tomsmith"
PASSWORD = "SuperSecretPassword!"


def main() -> None:
    with Browsers() as browsers:
        sample = browsers.launch("sample", SampleBrowserOptions)

        # open() は自分自身を返すので、開いてそのままログインまでチェーンできる
        # login() は SecurePage を返す → そのまま次の画面の操作が書ける
        secure = LoginPage(sample).open().login(username=USERNAME, password=PASSWORD)
        print("画面見出し:", secure.get_heading())
        print("メッセージ:", secure.get_flash_message())

        # logout() は LoginPage を返す（続けてログイン画面を操作する場合に使う）
        secure.logout()
        print("ログアウト完了")


if __name__ == "__main__":
    main()
