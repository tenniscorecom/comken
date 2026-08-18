"""
login_page.py — ログイン画面

【Page Object の書き方】
  - 画面に存在する要素のセレクターは Locator のクラス変数としてクラス上部に定義する
  - メソッドは「この画面でできること」だけを書く
  - 別の画面に移動するメソッドは、遷移先のページクラスを返す
  - 画面インスタンスを新しく作るときは `self.to(遷移先クラス)` を使う
    （書き方の正本は docs/browser.md）

【循環インポートの対処】
  画面クラス同士が互いを参照するときは循環インポートになるため、
  `from __future__ import annotations` を入れて注釈の評価を遅延し、
  ランタイムで実際にクラスが必要になるメソッド内だけで import する。
  他の画面で参照される側になったら、TYPE_CHECKING ブロックにも import を置く:

      from typing import TYPE_CHECKING

      if TYPE_CHECKING:
          from src.sites.example.pages.home_page import HomePage

【このファイルは書き換え前提のサンプル】
  このままでは example.co.jp のログイン画面向けに書かれたセレクターなので、
  自分のサイトに合わせ、以下の Locator・操作を置き換えること。
"""

# 戻り値などで他画面の型注釈を使うとき、`from __future__ import annotations` を入れて
# 注釈の評価を遅延する（上の「循環インポートの対処」を参照）。
from __future__ import annotations

from comken.toolbox.browser import Locator, Page


class LoginPage(Page):
    """ログイン画面のサンプル（書き換え前提）。

    Page を直接継承しているのは、この雛形に「サイト共通の基底クラス」を
    まだ作っていないから。1サイト目を立ち上げたあと、
    comken/toolbox/browser/sites/sample/pages/app_page.py のように
    `SitePage` を継承した共通クラス（例: `AppPage`）を作って、
    ここに切り替えるとよい。
    """

    # ── セレクター（F12 で確認した値をここに書く。画面変更時はここだけ直す） ──
    # ここを自分のサイトのログイン画面のセレクターに書き換える
    USERNAME = Locator.id("username")
    PASSWORD = Locator.id("password")
    LOGIN_BTN = Locator.css("button[type='submit']")

    def login(self, username: str, password: str) -> Page:
        """ログイン操作のサンプル。

        ログイン後に別の画面へ移るときは、戻り値をその画面クラスに変えて、
        メソッドの末尾で `return self.to(遷移先クラス)` を返す。
        戻り値を画面遷移に使うと、呼び出し側のコードがそのまま遷移図になる。

        この雛形ではサンプルとして `Page` を返している（=「ログイン後の画面は
        まだ決まっていない」を表す）。自分のサイトでは以下のように書く
        （絶対 import で。`from .home_page` のような相対 import は使わない）:

            def login(self, username: str, password: str) -> "HomePage":
                from src.sites.example.pages.home_page import HomePage

                self.input(self.USERNAME, username)
                self.input(self.PASSWORD, password)
                self.click(self.LOGIN_BTN)
                return self.to(HomePage)
        """
        self.input(self.USERNAME, username)
        self.input(self.PASSWORD, password)
        self.click(self.LOGIN_BTN)
        # ログイン後の画面が決まったら、下を `return self.to(HomePage)` などに変える
        return self
