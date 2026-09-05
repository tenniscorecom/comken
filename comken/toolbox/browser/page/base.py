"""comken/toolbox/browser/page/base.py — Page の共有状態と内部ヘルパー。

Page を構成する各 Mixin（navigation.py / operations.py / reading.py /
waiting.py / alerts.py / escape.py）はすべてこの _PageBase を継承する。
共有する状態（session / _wait_seconds / _wait）と、要素待機の失敗を
ElementNotFoundError に包み直す _until() をここに置く。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from comken.exceptions import ElementNotFoundError
from comken.toolbox.browser.locator import Locator
from comken.toolbox.browser.management import BrowserSession

# to() が「渡したクラスをそのまま返す」ことを型で示す
P = TypeVar("P", bound="_PageBase")


class _PageBase:
    """Page の共有状態（session / 待機設定）と内部ヘルパーを持つ。

    Attributes:
        session: この画面が乗っているブラウザ。遷移先の画面クラスを作るときに渡す。
    """

    def __init__(self, session: BrowserSession, wait_seconds: int | None = None) -> None:
        """
        Args:
            session: Browsers.launch() で起動したセッション。
            wait_seconds: 要素待機のタイムアウト秒数。
                          省略時はセッションの設定（BrowserOptions.WAIT_SECONDS）を引き継ぐ。
        """
        self.session = session
        self._wait_seconds = wait_seconds if wait_seconds is not None else session.wait_seconds
        self._wait = WebDriverWait(session.raw, self._wait_seconds)

    def to(self, page_class: type[P]) -> P:
        """遷移先の画面クラスを作る（同じブラウザを引き継ぐ）。

        画面が変わるメソッドの最後で使う。

            def login(self, user_id: str, password: str) -> HomePage:
                self.click(self.LOGIN_BUTTON)
                return self.to(HomePage)

        `HomePage(self.session)` と書いても同じだが、そう書くと画面クラスを
        1つ足すたびに「セッションとは何か」が顔を出す。画面の遷移を書きたい
        だけの人が、ブラウザの持ち方まで知らずに済むようにする。
        """
        return page_class(self.session)

    def _until(self, condition: Callable[[Any], Any], locator: object, description: str) -> Any:
        """条件が満たされるまで待つ。時間切れなら、どこで失敗したかを添えて送出する。

        selenium の TimeoutException はメッセージにセレクターが入らないため、
        ログだけを見る人が原因にたどり着けない。ここで包み直している。
        """
        try:
            return self._wait.until(condition)
        except TimeoutException as exc:
            raise ElementNotFoundError(locator, self._wait_seconds, description) from exc

    def _visible(self, locator: Locator) -> WebElement:
        """表示されるまで待って要素を返す。"""
        return self._until(EC.visibility_of_element_located(locator), locator, "表示され")

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(session={self.session.name!r})"
