"""comken/toolbox/browser/page/model.py — Page 本体（Mixin をまとめた基底クラス）。

画面ごとに Page を継承したクラスを作り、その画面でできることをメソッドにする。
セレクターは Locator のクラス変数としてクラスの先頭に並べる。
画面の HTML が変わったとき、直す場所がクラスの先頭に集まるようにするため。

    from comken.toolbox.browser import Locator, SitePage

    class LoginPage(SitePage):
        BASE_URL = "https://kintai.example.co.jp"

        USER_ID = Locator.id("userId")
        PASSWORD = Locator.id("password")
        LOGIN_BUTTON = Locator.css("button[type='submit']")

        def login(self, user_id: str, password: str) -> "HomePage":
            self.go("/login")
            self.input(self.USER_ID, user_id)
            self.input(self.PASSWORD, password)
            self.click(self.LOGIN_BUTTON)
            return HomePage(self.session)     # 遷移先の画面クラスを返す

画面が変わるメソッドは遷移先の画面クラスを返す。呼び出し側が画面の流れを
コードのまま追えるようにするため:

    home = LoginPage(session).login(user_id, password)
    days = home.open_attendance().unfilled_days()

要素の待機は自動で行われる（既定10秒、BrowserOptions.WAIT_SECONDS で変更）。
time.sleep で待たないこと。待ち時間が読めなくなり、遅いうえに不安定になる。

このクラスの実体は用途別に分けたファイルに分散している（読む場所を絞るため）:

    base.py        __init__ / to() / _until() / _visible()（共有状態と内部ヘルパー）
    navigation.py  open() / save_screenshot()
    operations.py  click() / input() / select_*() / drag_drop() / scroll_*()
    reading.py     read_*() / has_element() / count_elements()
    waiting.py     wait_visible() / wait_invisible()
    alerts.py      alert_*()
    escape.py      frame() / find_element*() / execute_script()（用意されていない操作の逃げ道）

利用側はこの分割を意識しなくてよい。
``from comken.toolbox.browser import Page`` でいつも通り1つのクラスとして使える。
"""

from __future__ import annotations

from comken.toolbox.browser.page.alerts import AlertsMixin
from comken.toolbox.browser.page.escape import EscapeMixin
from comken.toolbox.browser.page.navigation import NavigationMixin
from comken.toolbox.browser.page.operations import OperationsMixin
from comken.toolbox.browser.page.reading import ReadingMixin
from comken.toolbox.browser.page.waiting import WaitingMixin


class Page(
    NavigationMixin,
    OperationsMixin,
    ReadingMixin,
    WaitingMixin,
    AlertsMixin,
    EscapeMixin,
):
    """1画面ぶんの操作をまとめる基底クラス。画面ごとに継承して使う。

    要素は見つかるまで自動で待つ。時間内に見つからない場合は
    ElementNotFoundError になり、どのセレクターで失敗したかがメッセージに出る。

    Attributes:
        session: この画面が乗っているブラウザ。遷移先の画面クラスを作るときに渡す。
    """
