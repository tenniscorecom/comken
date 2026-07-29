"""
browser/base_page.py — Page Object の基底クラス

画面ごとに BasePage を継承したクラスを作り、その画面でできる操作をメソッドとして定義する。
セレクターは Locator のクラス変数として先頭にまとめる（画面変更時に直す場所が一箇所になる）。
セレクターの優先順位（Locator のファクトリも同じ順で選ぶ）:
    1. ID（Locator.id）
    2. name 属性（Locator.name）
    3. CSS セレクター（Locator.css）
    4. XPath（Locator.xpath）← 最終手段。絶対パスは使わない

従来のセレクター種別入りメソッド（click_id / input_css / text_xpath 等）もそのまま使える。
"""

from pathlib import Path
from typing import TYPE_CHECKING

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from comken.utils import now

from .locator import Locator

if TYPE_CHECKING:
    from .driver import EdgeDriver


class BasePage:
    """全 Page Object の基底クラス。画面ごとにこのクラスを継承して使う。

    要素が見つかるまで wait_seconds 秒まで自動で待機する（明示的待機・WebDriverWait）。
    """

    def __init__(self, driver: "EdgeDriver | WebDriver", wait_seconds: int | None = None) -> None:
        """
        Args:
            driver: EdgeDriver または生の WebDriver。
                    EdgeDriver をそのまま渡せる（LoginPage(d) と書ける）。
            wait_seconds: 要素待機のタイムアウト秒数。省略時は EdgeDriver の
                          WAIT_SECONDS（BrowserOptions の設定）を引き継ぐ。
                          生の WebDriver を渡した場合は 10 秒。
        """
        # EdgeDriver の WAIT_SECONDS を明示的待機の既定にする（unwrap する前に読む）
        if wait_seconds is None:
            wait_seconds = getattr(driver, "wait_seconds", 10)
        # EdgeDriver が渡されたら中の WebDriver を取り出す
        # （isinstance にしないのは driver.py との循環 import を避けるため）
        if hasattr(driver, "driver"):
            driver = driver.driver
        self._driver: WebDriver = driver
        self._wait = WebDriverWait(driver, wait_seconds)

    def open(self, url: str) -> "BasePage":
        """指定した URL を開き、自分自身を返す（メソッドチェーンできる）。"""
        self._driver.get(url)
        return self

    def save_screenshot(self, prefix: str = "error") -> Path:
        """スクリーンショットを logs/ フォルダに保存する。

        エラー発生時の状態記録に使う。

        Args:
            prefix: ファイル名のプレフィックス（デフォルト: "error"）。
                    保存先: logs/{prefix}_{YYYYmmdd_HHMMSS}.png

        Returns:
            保存したファイルのパス。
        """
        timestamp = now().strftime("%Y%m%d_%H%M%S")
        path = Path("logs") / f"{prefix}_{timestamp}.png"
        path.parent.mkdir(exist_ok=True)
        self._driver.save_screenshot(str(path))
        return path

    # -------------------------------------------------- Locator 版（推奨）
    # セレクターを Locator のクラス変数として宣言し、これらのメソッドに渡す。
    # （従来の click_id / input_css 等もそのまま使える）

    def click(self, locator: Locator, index: int = 0) -> None:
        """Locator で指定した要素をクリックする。

        Args:
            locator: Locator（例: Locator.id("login-btn")）。
            index: 複数一致する場合に何番目をクリックするか（0始まり）。
        """
        self._click_at(locator.by, locator.value, index)

    def input(self, locator: Locator, text: str) -> None:
        """Locator で指定した入力欄にテキストを入力する（既存の値はクリアされる）。"""
        self._input(locator.by, locator.value, text)

    def text(self, locator: Locator) -> str:
        """Locator で指定した要素のテキストを返す。"""
        return self._text(locator.by, locator.value)

    def texts(self, locator: Locator) -> list[str]:
        """Locator に一致する全要素のテキストをリストで返す。"""
        return self._texts(locator.by, locator.value)

    def has(self, locator: Locator) -> bool:
        """Locator の要素が DOM 上に存在するか返す（表示非表示は問わない）。"""
        return self._has(locator.by, locator.value)

    def count(self, locator: Locator) -> int:
        """Locator に一致する要素の数を返す（0件なら 0。待機しない）。"""
        return len(self._driver.find_elements(locator.by, locator.value))

    def select_text(self, locator: Locator, text: str) -> None:
        """Locator の <select> をテキストで選択する。"""
        self._select_text(locator.by, locator.value, text)

    def select_value(self, locator: Locator, option_value: str) -> None:
        """Locator の <select> を value 属性で選択する。"""
        self._select_value(locator.by, locator.value, option_value)

    def select_index(self, locator: Locator, index: int) -> None:
        """Locator の <select> をインデックスで選択する（0始まり）。"""
        self._select_index(locator.by, locator.value, index)

    def wait_visible(self, locator: Locator) -> None:
        """Locator の要素が表示されるまで待機する（モーダルが開くのを待つ等）。"""
        self._wait.until(EC.visibility_of_element_located(tuple(locator)))

    def wait_invisible(self, locator: Locator) -> None:
        """Locator の要素が非表示になるまで待機する（モーダルが閉じるのを待つ等）。"""
        self._wait.until(EC.invisibility_of_element_located(tuple(locator)))

    def scroll_to(self, locator: Locator) -> None:
        """Locator の要素が見えるようにスクロールする。"""
        el = self._driver.find_element(locator.by, locator.value)
        self._driver.execute_script("arguments[0].scrollIntoView(true);", el)

    # ------------------------------------------------------------------ click
    def click_id(self, value: str, index: int = 0) -> None:
        """id 属性でクリックする。

        Args:
            value: id 属性の値。
            index: 同じ id の要素が複数ある場合に何番目をクリックするか（0始まり）。
                   本来 id は一意だが、そうなっていない画面への対処用。
        """
        self._click_at(By.ID, value, index)

    def click_name(self, value: str, index: int = 0) -> None:
        """name 属性でクリックする。

        Args:
            value: name 属性の値。
            index: 複数一致する場合に何番目をクリックするか（0始まり）。
        """
        self._click_at(By.NAME, value, index)

    def click_css(self, value: str, index: int = 0) -> None:
        """CSS セレクターでクリックする。

        Args:
            value: CSS セレクター。
            index: 同じセレクターに複数の要素が一致する場合、何番目をクリックするか（0始まり）。
                   基本はセレクター側で一意に絞り込み、index は最終手段として使う。
        """
        self._click_at(By.CSS_SELECTOR, value, index)

    def click_xpath(self, value: str, index: int = 0) -> None:
        """XPath でクリックする。

        Args:
            value: XPath。
            index: 複数一致する場合に何番目をクリックするか（0始まり）。
        """
        self._click_at(By.XPATH, value, index)

    # ------------------------------------------------------------------ input
    def input_id(self, value: str, text: str) -> None:
        """id 属性の入力欄にテキストを入力する（既存の値はクリアされる）。"""
        self._input(By.ID, value, text)

    def input_name(self, value: str, text: str) -> None:
        """name 属性の入力欄にテキストを入力する（既存の値はクリアされる）。"""
        self._input(By.NAME, value, text)

    def input_css(self, value: str, text: str) -> None:
        """CSS セレクターの入力欄にテキストを入力する（既存の値はクリアされる）。"""
        self._input(By.CSS_SELECTOR, value, text)

    def input_xpath(self, value: str, text: str) -> None:
        """XPath の入力欄にテキストを入力する（既存の値はクリアされる）。"""
        self._input(By.XPATH, value, text)

    # ---------------------------------------------------------------- get_text
    def text_id(self, value: str) -> str:
        """id 属性の要素のテキストを返す。"""
        return self._text(By.ID, value)

    def text_name(self, value: str) -> str:
        """name 属性の要素のテキストを返す。"""
        return self._text(By.NAME, value)

    def text_css(self, value: str) -> str:
        """CSS セレクターの要素のテキストを返す。"""
        return self._text(By.CSS_SELECTOR, value)

    def text_xpath(self, value: str) -> str:
        """XPath の要素のテキストを返す。"""
        return self._text(By.XPATH, value)

    # --------------------------------------------------------------- select
    def select_text_id(self, value: str, text: str) -> None:
        """id 属性の <select> をテキストで選択する。"""
        self._select_text(By.ID, value, text)

    def select_text_name(self, value: str, text: str) -> None:
        """name 属性の <select> をテキストで選択する。"""
        self._select_text(By.NAME, value, text)

    def select_text_css(self, value: str, text: str) -> None:
        """CSS セレクターの <select> をテキストで選択する。"""
        self._select_text(By.CSS_SELECTOR, value, text)

    def select_text_xpath(self, value: str, text: str) -> None:
        """XPath の <select> をテキストで選択する。"""
        self._select_text(By.XPATH, value, text)

    def select_value_id(self, value: str, option_value: str) -> None:
        """id 属性の <select> を value 属性で選択する。"""
        self._select_value(By.ID, value, option_value)

    def select_value_name(self, value: str, option_value: str) -> None:
        """name 属性の <select> を value 属性で選択する。"""
        self._select_value(By.NAME, value, option_value)

    def select_value_css(self, value: str, option_value: str) -> None:
        """CSS セレクターの <select> を value 属性で選択する。"""
        self._select_value(By.CSS_SELECTOR, value, option_value)

    def select_value_xpath(self, value: str, option_value: str) -> None:
        """XPath の <select> を value 属性で選択する。"""
        self._select_value(By.XPATH, value, option_value)

    def select_index_id(self, value: str, index: int) -> None:
        """id 属性の <select> をインデックスで選択する（0始まり）。"""
        self._select_index(By.ID, value, index)

    def select_index_name(self, value: str, index: int) -> None:
        """name 属性の <select> をインデックスで選択する（0始まり）。"""
        self._select_index(By.NAME, value, index)

    def select_index_css(self, value: str, index: int) -> None:
        """CSS セレクターの <select> をインデックスで選択する（0始まり）。"""
        self._select_index(By.CSS_SELECTOR, value, index)

    def select_index_xpath(self, value: str, index: int) -> None:
        """XPath の <select> をインデックスで選択する（0始まり）。"""
        self._select_index(By.XPATH, value, index)

    def select_radio_name(self, name: str, value: str) -> None:
        """name 属性と value 属性でラジオボタンを選択する。

        Args:
            name: ラジオボタングループの name 属性。
            value: 選択する option の value 属性。
        """
        self._click(By.CSS_SELECTOR, f"input[type='radio'][name='{name}'][value='{value}']")

    # ------------------------------------------------------------------ alert
    def alert_accept(self) -> None:
        """アラートを承認（OK）する。アラートが表示されるまで待機する。"""
        self._wait.until(EC.alert_is_present()).accept()

    def alert_dismiss(self) -> None:
        """アラートをキャンセルする。アラートが表示されるまで待機する。"""
        self._wait.until(EC.alert_is_present()).dismiss()

    def alert_text(self) -> str:
        """アラートのテキストを返す。アラートが表示されるまで待機する。"""
        return self._wait.until(EC.alert_is_present()).text

    # ------------------------------------------------------------------- wait
    def wait_visible_id(self, value: str) -> None:
        """id 属性の要素が表示されるまで待機する（モーダルが開くのを待つ等）。"""
        self._wait.until(EC.visibility_of_element_located((By.ID, value)))

    def wait_visible_css(self, value: str) -> None:
        """CSS セレクターの要素が表示されるまで待機する。"""
        self._wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, value)))

    def wait_visible_xpath(self, value: str) -> None:
        """XPath の要素が表示されるまで待機する。"""
        self._wait.until(EC.visibility_of_element_located((By.XPATH, value)))

    def wait_invisible_css(self, value: str) -> None:
        """CSS セレクターの要素が非表示になるまで待機する（モーダルが閉じるのを待つ等）。"""
        self._wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, value)))

    def wait_invisible_xpath(self, value: str) -> None:
        """XPath の要素が非表示になるまで待機する。"""
        self._wait.until(EC.invisibility_of_element_located((By.XPATH, value)))

    # -------------------------------------------------------------------- has
    def has_id(self, value: str) -> bool:
        """id 属性の要素が DOM 上に存在するか返す（表示非表示は問わない）。"""
        return self._has(By.ID, value)

    def has_css(self, value: str) -> bool:
        """CSS セレクターの要素が DOM 上に存在するか返す。"""
        return self._has(By.CSS_SELECTOR, value)

    def has_xpath(self, value: str) -> bool:
        """XPath の要素が DOM 上に存在するか返す。"""
        return self._has(By.XPATH, value)

    # ----------------------------------------------------------- 複数要素の扱い
    # 同じセレクターに複数の要素が一致する場合に使う。
    # 第一選択はセレクター側で一意に絞り込むこと（例: "table tr:nth-child(2) .name"）。
    # 本来 id は一意だが、複数ある画面も実在するため id 版も用意している。
    def count_id(self, value: str) -> int:
        """id 属性に一致する要素の数を返す（0件なら 0。待機しない）。"""
        return len(self._driver.find_elements(By.ID, value))

    def count_css(self, value: str) -> int:
        """CSS セレクターに一致する要素の数を返す（0件なら 0。待機しない）。"""
        return len(self._driver.find_elements(By.CSS_SELECTOR, value))

    def count_xpath(self, value: str) -> int:
        """XPath に一致する要素の数を返す（0件なら 0。待機しない）。"""
        return len(self._driver.find_elements(By.XPATH, value))

    def texts_id(self, value: str) -> list[str]:
        """id 属性に一致する全要素のテキストをリストで返す。"""
        return self._texts(By.ID, value)

    def texts_css(self, value: str) -> list[str]:
        """CSS セレクターに一致する全要素のテキストをリストで返す。

        一覧テーブルの全行のテキストを取る場合などに使う。
        """
        return self._texts(By.CSS_SELECTOR, value)

    def texts_xpath(self, value: str) -> list[str]:
        """XPath に一致する全要素のテキストをリストで返す。"""
        return self._texts(By.XPATH, value)

    # ----------------------------------------------------------------- scroll
    def scroll_to_css(self, value: str) -> None:
        """CSS セレクターの要素が見えるようにスクロールする。"""
        el = self._driver.find_element(By.CSS_SELECTOR, value)
        self._driver.execute_script("arguments[0].scrollIntoView(true);", el)

    def scroll_to_id(self, value: str) -> None:
        """id 属性の要素が見えるようにスクロールする。"""
        el = self._driver.find_element(By.ID, value)
        self._driver.execute_script("arguments[0].scrollIntoView(true);", el)

    def scroll_bottom(self) -> None:
        """ページの一番下までスクロールする（無限スクロールのトリガー等）。"""
        self._driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

    # --------------------------------------------------------------- drag_drop
    def drag_drop_css(self, source: str, target: str) -> None:
        """CSS セレクターで指定した要素をドラッグ＆ドロップする。

        Args:
            source: ドラッグ元の CSS セレクター。
            target: ドロップ先の CSS セレクター。
        """
        src = self._wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, source)))
        tgt = self._wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, target)))
        ActionChains(self._driver).drag_and_drop(src, tgt).perform()

    # --------------------------------------------------------------------- js
    def js(self, script: str, *args) -> object:
        """JavaScript を実行する。

        Args:
            script: 実行する JavaScript 文字列。
            *args: スクリプト内で arguments[0], arguments[1] ... として参照できる引数。

        Returns:
            JavaScript の return 値。
        """
        return self._driver.execute_script(script, *args)

    # ----------------------------------------------------------- private base
    def _click(self, by: str, value: str) -> None:
        self._wait.until(EC.element_to_be_clickable((by, value))).click()

    def _click_at(self, by: str, value: str, index: int) -> None:
        if index == 0:
            self._click(by, value)
            return
        elements = self._wait.until(EC.presence_of_all_elements_located((by, value)))
        elements[index].click()

    def _texts(self, by: str, value: str) -> list[str]:
        elements = self._wait.until(EC.presence_of_all_elements_located((by, value)))
        return [el.text for el in elements]

    def _input(self, by: str, value: str, text: str) -> None:
        el = self._wait.until(EC.visibility_of_element_located((by, value)))
        el.clear()
        el.send_keys(text)

    def _text(self, by: str, value: str) -> str:
        return self._wait.until(EC.visibility_of_element_located((by, value))).text

    def _select_text(self, by: str, value: str, text: str) -> None:
        el = self._wait.until(EC.visibility_of_element_located((by, value)))
        Select(el).select_by_visible_text(text)

    def _select_value(self, by: str, value: str, option_value: str) -> None:
        el = self._wait.until(EC.visibility_of_element_located((by, value)))
        Select(el).select_by_value(option_value)

    def _select_index(self, by: str, value: str, index: int) -> None:
        el = self._wait.until(EC.visibility_of_element_located((by, value)))
        Select(el).select_by_index(index)

    def _has(self, by: str, value: str) -> bool:
        try:
            self._driver.find_element(by, value)
            return True
        except NoSuchElementException:
            return False
