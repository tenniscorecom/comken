"""comken/toolbox/browser/page/reading.py — 画面から値を読む（read_* / has_element など）。"""

from __future__ import annotations

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support import expected_conditions as EC

from comken.toolbox.browser.locator import Locator
from comken.toolbox.browser.page.base import _PageBase


class ReadingMixin(_PageBase):
    """画面から値を読む（read_* / has_element / count_elements）。"""

    def read_text(self, locator: Locator) -> str:
        """要素の表示文字を返す。"""
        with self.session._operating(f"read_text({locator})"):
            return self._until(EC.visibility_of_element_located(locator), locator, "表示され").text

    def read_texts(self, locator: Locator) -> list[str]:
        """一致する全要素の表示文字をリストで返す（一覧表の全行を読むときなど）。"""
        with self.session._operating(f"read_texts({locator})"):
            elements = self._until(
                EC.presence_of_all_elements_located(locator), locator, "見つかり"
            )
            return [element.text for element in elements]

    def read_attribute(self, locator: Locator, name: str) -> str | None:
        """要素の属性値を返す（href やチェック状態など）。属性が無ければ None。

        Args:
            locator: 対象のセレクター。
            name: 属性名（例: "href", "value", "checked"）。
        """
        with self.session._operating(f"read_attribute({locator}, {name})"):
            element = self._until(EC.presence_of_element_located(locator), locator, "見つかり")
            return element.get_attribute(name)

    def has_element(self, locator: Locator) -> bool:
        """要素が HTML 上に在るかを返す（待たずにその場で確認する）。

        「在れば押す」のような分岐に使う。表示されているかどうかは見ない。
        """
        with self.session._operating(f"has_element({locator})"):
            try:
                self.session.raw.find_element(*locator)
                return True
            except NoSuchElementException:
                return False

    def count_elements(self, locator: Locator) -> int:
        """一致する要素の数を返す（待たずにその場で数える。無ければ 0）。"""
        with self.session._operating(f"count_elements({locator})"):
            return len(self.session.raw.find_elements(*locator))
