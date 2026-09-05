"""comken/toolbox/browser/page/operations.py — 要素の操作（click / input / select など）。"""

from __future__ import annotations

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select

from comken.toolbox.browser.locator import Locator
from comken.toolbox.browser.page.base import _PageBase


class OperationsMixin(_PageBase):
    """要素の操作（click / input / select / drag_drop / scroll）。"""

    def click(self, locator: Locator, index: int = 0) -> None:
        """要素をクリックする。クリックできる状態になるまで待つ。

        Args:
            locator: 対象のセレクター。
            index: 同じセレクターに複数の要素が一致する場合、何番目か（0始まり）。
                   まずはセレクター側で1つに絞り込み、index は最後の手段にする。
        """
        with self.session._operating(f"click({locator})"):
            if index == 0:
                condition = EC.element_to_be_clickable(locator)
                self._until(condition, locator, "クリックでき").click()
                return
            elements = self._until(
                EC.presence_of_all_elements_located(locator), locator, "見つかり"
            )
            elements[index].click()

    def input(self, locator: Locator, text: str) -> None:
        """入力欄に文字を入れる。もとの値は消える。"""
        with self.session._operating(f"input({locator})"):
            element = self._visible(locator)
            element.clear()
            element.send_keys(text)

    def select_text(self, locator: Locator, text: str) -> None:
        """プルダウンを、表示されている文字で選ぶ。"""
        with self.session._operating(f"select_text({locator})"):
            Select(self._visible(locator)).select_by_visible_text(text)

    def select_value(self, locator: Locator, option_value: str) -> None:
        """プルダウンを、option の value 属性で選ぶ。"""
        with self.session._operating(f"select_value({locator})"):
            Select(self._visible(locator)).select_by_value(option_value)

    def select_index(self, locator: Locator, index: int) -> None:
        """プルダウンを、上から何番目かで選ぶ（0始まり）。"""
        with self.session._operating(f"select_index({locator})"):
            Select(self._visible(locator)).select_by_index(index)

    def drag_drop(self, source: Locator, target: Locator) -> None:
        """要素を別の要素までドラッグして落とす。"""
        with self.session._operating(f"drag_drop({source} → {target})"):
            ActionChains(self.session.raw).drag_and_drop(
                self._visible(source), self._visible(target)
            ).perform()

    def scroll_to(self, locator: Locator) -> None:
        """要素が画面に入るまでスクロールする。"""
        with self.session._operating(f"scroll_to({locator})"):
            element = self._until(EC.presence_of_element_located(locator), locator, "見つかり")
            self.session.raw.execute_script("arguments[0].scrollIntoView(true);", element)

    def scroll_bottom(self) -> None:
        """ページの一番下までスクロールする（続きを読み込ませるときなど）。"""
        with self.session._operating("scroll_bottom"):
            self.session.raw.execute_script("window.scrollTo(0, document.body.scrollHeight);")
