"""
サンプル: ログイン → セキュアエリア確認 → ログアウト

実行方法:
    リポジトリのルートで python -m examples.sample_login.run

画面へ移るときは `SiteBase` の `go_〇〇()` から始める
（書き方の正本は docs/browser.md）。
"""

from comken.toolbox.browser import Browsers
from comken.toolbox.browser.sites import SampleSite

USERNAME = "tomsmith"
PASSWORD = "SuperSecretPassword!"


def main() -> None:
    with Browsers() as browsers:
        sample = browsers.launch(SampleSite)

        # go_login() は LoginPage を返す → login() で SecurePage へ
        secure = sample.go_login().login(username=USERNAME, password=PASSWORD)
        print("画面見出し:", secure.get_heading())
        print("メッセージ:", secure.get_flash_message())

        # logout() は LoginPage を返す（続けてログイン画面を操作する場合に使う）
        secure.logout()
        print("ログアウト完了")


if __name__ == "__main__":
    main()
