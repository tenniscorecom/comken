"""comken/toolbox/browser/page/waiting.py — 表示・非表示を待つ（wait_visible / wait_invisible）。"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING, TypeAlias

from selenium.webdriver.support import expected_conditions as EC

from comken.exceptions import ElementNotFoundError
from comken.toolbox.browser.locator import Locator
from comken.toolbox.browser.page.base import _PageBase

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from selenium.webdriver.remote.webdriver import WebDriver

    Condition: TypeAlias = Callable[[WebDriver], bool]

logger = logging.getLogger(__name__)


class WaitingMixin(_PageBase):
    """表示・非表示を待つ（wait_visible / wait_invisible / wait_until_any）。"""

    def wait_visible(self, locator: Locator) -> None:
        """要素が表示されるまで待つ（画面が開くのを待つときなど）。"""
        logger.debug("要素の表示を待ちます: locator=%s timeout=%d秒", locator, self._wait_seconds)
        with self.session._operating(f"wait_visible({locator})"):
            self._until(EC.visibility_of_element_located(locator), locator, "表示され")
        logger.debug("要素が表示されました: locator=%s", locator)

    def wait_invisible(self, locator: Locator) -> None:
        """要素が消えるまで待つ（読み込み中の表示が消えるのを待つときなど）。"""
        logger.debug("要素の消失を待ちます: locator=%s timeout=%d秒", locator, self._wait_seconds)
        with self.session._operating(f"wait_invisible({locator})"):
            self._until(EC.invisibility_of_element_located(locator), locator, "消え")
        logger.debug("要素が消えました: locator=%s", locator)

    def url_changed(self, url_before: str) -> Condition:
        """URL が url_before から変わったことを表す条件（wait_until_any へ渡す）。"""
        return EC.url_changes(url_before)

    @contextmanager
    def wait_for_url_change(self) -> Iterator[None]:
        """with に入った時点の URL から、抜けるまでに変わるのを待つ。

        「操作前の URL を変数に取っておいて、操作後に渡す」手間を無くしたもの。
        変わらなければ通常どおり ElementNotFoundError になる。

            with self.wait_for_url_change():
                self.click(self.NEXT_BTN)
        """
        url_before = self.session.current_url
        yield
        try:
            self.wait_until_any(self.url_changed(url_before))
        except ElementNotFoundError as error:
            # wait_until_any() のメッセージは条件オブジェクトの羅列で読みにくいため、
            # url_before に詰め替える（_until() が TimeoutException を包み直すのと同じ形）
            raise ElementNotFoundError(url_before, self._wait_seconds, "URLが変わり") from error

    def text_shown(self, locator: Locator) -> Condition:
        """locator の要素の表示文字が空でないことを表す条件（wait_until_any へ渡す）。

        要素の「存在」ではなく「表示文字が空でないか」で判定する
        （``raise_if_shown()`` と判定基準を合わせている）。コンテナが先に
        空のままDOMへ出て、文字は後から入る画面でも誤判定しない。

        見つからない間の ``NoSuchElementException`` は WebDriverWait が既定で
        無視して待ち続けるため、ここで拾う必要はない。
        """
        return lambda driver: bool(driver.find_element(*locator).text)

    def wait_until_any(self, *conditions: Condition) -> None:
        """conditions のうち、どれか一つが最初に真になるまで待つ。

        url_changed() / text_shown() など、このクラスが用意する条件と組み合わせる
        （Selenium の expected_conditions を呼び出し側で直接 import しなくてよいように
        するため）。

            url_before = self.session.current_url
            self.click(self.SEARCH_BTN)
            self.wait_until_any(self.url_changed(url_before), self.text_shown(self.NO_RESULT_MSG))
        """
        with self.session._operating("wait_until_any(...)"):
            self._until(EC.any_of(*conditions), conditions, "いずれかの条件が満たされ")
        logger.debug("いずれかの条件が満たされました: 条件数=%d", len(conditions))

    def wait_for_result(self, url_before: str, error_locator: Locator) -> None:
        """フォーム送信の結果が出るまで待つ:「URL が変わる」か「error_locator の
        表示文字が出る」のどちらか早い方が起きた時点で確定する。

        結果が Ajax 等で少し遅れて出る画面で、送信直後に一度だけ確認すると
        表示の遅れをすり抜けてしまう（実際は失敗しているのに成功と判定して
        しまう）のを防ぐために使う。早い方が起きた時点で確定するので、
        成功時に無駄な待ちは発生しない。

        「URL変化・エラー表示」のよくある2択専用の短縮形。それ以外の組み合わせで
        待ちたいときは wait_until_any() を直接使う。

            url_before = self.session.current_url
            self.click(self.LOGIN_BTN)
            self.wait_for_result(url_before, self.ERROR_MSG)
            self.raise_if_shown(self.ERROR_MSG, LoginFailedError)
        """
        try:
            self.wait_until_any(self.url_changed(url_before), self.text_shown(error_locator))
        except ElementNotFoundError as error:
            # wait_until_any() のメッセージは条件オブジェクトの羅列で読みにくいため、
            # error_locator に詰め替える（_until() が TimeoutException を包み直すのと同じ形）
            raise ElementNotFoundError(error_locator, self._wait_seconds, "結果が確定し") from error
        logger.debug(
            "結果が確定しました: url_before=%s error_locator=%s", url_before, error_locator
        )
