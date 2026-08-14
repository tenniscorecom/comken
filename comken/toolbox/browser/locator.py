"""comken/toolbox/browser/locator.py — セレクターの宣言的管理

Page Object のセレクターをクラス変数として一箇所にまとめるための型。
画面変更でセレクターが変わったとき、直す場所がクラスの先頭に集まる。
NamedTuple なので selenium にそのまま展開できる:
    driver.find_element(*LoginPage.LOGIN_BTN)
"""

# 定義中の Locator を戻り値の型注釈に使うため、注釈の評価を遅延する。
from __future__ import annotations

from typing import NamedTuple

from selenium.webdriver.common.by import By


class Locator(NamedTuple):
    """セレクター（探し方 + 値）。Locator.id(...) 等のファクトリで作る。

    セレクターの優先順位（CONVENTIONS.md と同じ）:
        1. Locator.id      … id 属性
        2. Locator.name    … name 属性
        3. Locator.css     … CSS セレクター
        4. Locator.xpath   … XPath（最終手段。絶対パスは使わない）
    """

    by: str
    value: str

    @classmethod
    def id(cls, value: str) -> Locator:
        """id 属性で探す（例: Locator.id("login-btn")）。"""
        return cls(By.ID, value)

    @classmethod
    def name(cls, value: str) -> Locator:
        """name 属性で探す（例: Locator.name("username")）。"""
        return cls(By.NAME, value)

    @classmethod
    def css(cls, value: str) -> Locator:
        """CSS セレクターで探す（例: Locator.css("table tr .name")）。"""
        return cls(By.CSS_SELECTOR, value)

    @classmethod
    def xpath(cls, value: str) -> Locator:
        """XPath で探す（最終手段。例: Locator.xpath("//button[text()='検索']")）。"""
        return cls(By.XPATH, value)

    def __repr__(self) -> str:
        return f"Locator({self.by!r}, {self.value!r})"
