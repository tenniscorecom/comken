"""comken/toolbox/browser/page/escape.py — 用意されていない操作をするための逃げ道。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Self

from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC

from comken.toolbox.browser.locator import Locator
from comken.toolbox.browser.page.base import _PageBase


class EscapeMixin(_PageBase):
    """用意されていない操作をするための逃げ道（frame / find_element* / execute_script）。"""

    @contextmanager
    def frame(self, locator: Locator) -> Iterator[Self]:
        """iframe の中を操作し、抜けるときに元の画面へ戻る。

        iframe の中の要素は、切り替えないと見つからない。
        ElementNotFoundError が出て、HTML 上には要素があるのに掴めないときは
        たいていこれが原因:

            with page.frame(page.CONTENT_FRAME):
                page.click(page.SAVE_BUTTON)
            # 元の画面へ戻る（中で例外が出ても戻る）

        Yields:
            自分自身。中では今までどおりメソッドを呼べる。
        """
        with self.session._operating(f"frame({locator})"):
            self._until(EC.frame_to_be_available_and_switch_to_it(locator), locator, "切り替えられ")
            try:
                yield self
            finally:
                self.session.raw.switch_to.default_content()

    def find_element(self, locator: Locator) -> WebElement:
        """selenium の WebElement をそのまま返す。

        このクラスに用意されていない操作をするときの逃げ道。
        よく使うものはこのクラスにメソッドとして足すこと。
        """
        with self.session._operating(f"find_element({locator})"):
            return self._until(EC.presence_of_element_located(locator), locator, "見つかり")

    def find_elements(self, locator: Locator) -> list[WebElement]:
        """一致する全要素を WebElement のリストで返す。1件見つかるまで待つ。

        一覧表の行を1行ずつ処理するときに使う。行の中をさらに探すときは、
        行の WebElement から find_element(*Locator) で絞り込む:

            for row in page.find_elements(page.ROWS):
                if "未提出" in row.text:
                    row.find_element(*page.EDIT_BUTTON).click()

        まず値を読むだけなら read_texts() のほうが簡単で、
        「何番目かをクリックする」だけなら click(locator, index=...) で足りる。

        Args:
            locator: 対象のセレクター。

        Returns:
            見つかった要素のリスト（画面に並んでいる順）。

        Raises:
            ElementNotFoundError: 1件も見つからないまま待ち時間が過ぎた場合。
                                  0件がありうる場面では、表そのものが出るのを wait_visible() で
                                  待ってから count_elements() で件数を確認する。
                                  count_elements() は待たないので、
                                  読み込み前に呼ぶと「まだ出ていない」を「0件」と読み違える。
        """
        with self.session._operating(f"find_elements({locator})"):
            return self._until(EC.presence_of_all_elements_located(locator), locator, "見つかり")

    def execute_script(self, script: str, *args: object) -> object:
        """JavaScript を実行して戻り値を返す。

        Args:
            script: 実行する JavaScript。
            *args: スクリプト内で arguments[0], arguments[1] ... として参照できる値。
        """
        with self.session._operating("execute_script"):
            return self.session.raw.execute_script(script, *args)
