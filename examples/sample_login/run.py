"""
サンプル: ログイン → セキュアエリア確認 → ログアウト

実行方法:
    リポジトリのルートで python -m examples.sample_login.run

サイト固有の値は Site サブクラスに集める。launch に Site を渡すと
戻り値の `kintai.session` から BrowserSession に繋がる。
"""

from comken.toolbox.browser import Browsers
from examples.sample_login.pages.login_page import LoginPage
from examples.sample_login.sample_site import SampleSite

USERNAME = "tomsmith"
PASSWORD = "SuperSecretPassword!"


def main() -> None:
    with Browsers() as browsers:
        sample = browsers.launch(SampleSite)

        # open() は自分自身を返すので、開いてそのままログインまでチェーンできる
        # login() は SecurePage を返す → そのまま次の画面の操作が書ける
        secure = LoginPage(sample.session).open().login(username=USERNAME, password=PASSWORD)
        print("画面見出し:", secure.get_heading())
        print("メッセージ:", secure.get_flash_message())

        # logout() は LoginPage を返す（続けてログイン画面を操作する場合に使う）
        secure.logout()
        print("ログアウト完了")


if __name__ == "__main__":
    main()
