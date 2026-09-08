"""comken/toolbox/browser/page/escape.py — 用意されていない操作をするための逃げ道。"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Self

from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC

from comken.toolbox.browser.locator import Locator
from comken.toolbox.browser.page.base import _PageBase

logger = logging.getLogger(__name__)


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
        logger.debug("iframe へ切り替えます: locator=%s", locator)
        with self.session._operating(f"frame({locator})"):
            self._until(EC.frame_to_be_available_and_switch_to_it(locator), locator, "切り替えられ")
            try:
                yield self
            finally:
                self.session.raw.switch_to.default_content()
                logger.debug("iframe から戻りました: locator=%s", locator)

    def find_element(self, locator: Locator) -> WebElement:
        """selenium の WebElement をそのまま返す。

        このクラスに用意されていない操作をするときの逃げ道。
        よく使うものはこのクラスにメソッドとして足すこと。
        """
        with self.session._operating(f"find_element({locator})"):
            element = self._until(EC.presence_of_element_located(locator), locator, "見つかり")
            logger.debug("find_element で取得しました: locator=%s", locator)
            return element

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
            elements = self._until(
                EC.presence_of_all_elements_located(locator), locator, "見つかり"
            )
            logger.debug("find_elements で取得しました: locator=%s 件数=%d", locator, len(elements))
            return elements

    def execute_script(self, script: str, *args: object) -> object:
        """JavaScript を実行して戻り値を返す。

        Args:
            script: 実行する JavaScript。
            *args: スクリプト内で arguments[0], arguments[1] ... として参照できる値。
        """
        # script の中身は秘匿情報が埋め込まれている可能性もあるのでログには出さない
        logger.debug(
            "JavaScript を実行します: length=%d 引数=%d個",
            len(script),
            len(args),
        )
        with self.session._operating("execute_script"):
            result = self.session.raw.execute_script(script, *args)
            logger.debug(
                "JavaScript の実行が完了しました: length=%d 戻り値=%s",
                len(script),
                type(result).__name__,
            )
            return result
