"""comken/toolbox/browser/page.py — Page — 1画面ぶんの操作をまとめる基底クラス（Page Object）。

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
"""

# 定義中の Page と SitePage を型注釈に使うため、注釈の評価を遅延する。
from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Self

from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from ...exceptions import ElementNotFoundError
from .locator import Locator
from .management import BrowserSession

logger = logging.getLogger(__name__)


class Page:
    """1画面ぶんの操作をまとめる基底クラス。画面ごとに継承して使う。

    要素は見つかるまで自動で待つ。時間内に見つからない場合は
    ElementNotFoundError になり、どのセレクターで失敗したかがメッセージに出る。

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

    # ------------------------------------------------------------ 画面の移動

    def open(self, url: str) -> Self:
        """URL を開き、自分自身を返す。"""
        self.session.open(url)
        return self

    def save_screenshot(self, prefix: str = "screenshot") -> Path:
        """今の画面を logs/ に PNG で保存し、そのパスを返す。"""
        return self.session.save_screenshot(prefix)

    # ------------------------------------------------------------ 操作

    def click(self, locator: Locator, index: int = 0) -> None:
        """要素をクリックする。クリックできる状態になるまで待つ。

        Args:
            locator: 対象のセレクター。
            index: 同じセレクターに複数の要素が一致する場合、何番目か（0始まり）。
                   まずはセレクター側で1つに絞り込み、index は最後の手段にする。
        """
        with self.session._operating(f"click({locator})"):
            if index == 0:
                condition = EC.element_to_be_clickable(tuple(locator))
                self._until(condition, locator, "クリックでき").click()
                return
            elements = self._until(
                EC.presence_of_all_elements_located(tuple(locator)), locator, "見つかり"
            )
            elements[index].click()

    def input(self, locator: Locator, text: str) -> None:
        """入力欄に文字を入れる。もとの値は消える。"""
        with self.session._operating(f"input({locator})"):
            element = self._visible(locator)
            element.clear()
            element.send_keys(text)

    def read_text(self, locator: Locator) -> str:
        """要素の表示文字を返す。"""
        with self.session._operating(f"read_text({locator})"):
            return self._until(
                EC.visibility_of_element_located(tuple(locator)), locator, "表示され"
            ).text

    def read_texts(self, locator: Locator) -> list[str]:
        """一致する全要素の表示文字をリストで返す（一覧表の全行を読むときなど）。"""
        with self.session._operating(f"read_texts({locator})"):
            elements = self._until(
                EC.presence_of_all_elements_located(tuple(locator)), locator, "見つかり"
            )
            return [element.text for element in elements]

    def read_attribute(self, locator: Locator, name: str) -> str | None:
        """要素の属性値を返す（href やチェック状態など）。属性が無ければ None。

        Args:
            locator: 対象のセレクター。
            name: 属性名（例: "href", "value", "checked"）。
        """
        with self.session._operating(f"read_attribute({locator}, {name})"):
            element = self._until(
                EC.presence_of_element_located(tuple(locator)), locator, "見つかり"
            )
            return element.get_attribute(name)

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
            element = self._until(
                EC.presence_of_element_located(tuple(locator)), locator, "見つかり"
            )
            self.session.raw.execute_script("arguments[0].scrollIntoView(true);", element)

    def scroll_bottom(self) -> None:
        """ページの一番下までスクロールする（続きを読み込ませるときなど）。"""
        with self.session._operating("scroll_bottom"):
            self.session.raw.execute_script("window.scrollTo(0, document.body.scrollHeight);")

    # ------------------------------------------------------------ 確認・待機

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

    def wait_visible(self, locator: Locator) -> None:
        """要素が表示されるまで待つ（画面が開くのを待つときなど）。"""
        with self.session._operating(f"wait_visible({locator})"):
            self._until(EC.visibility_of_element_located(tuple(locator)), locator, "表示され")

    def wait_invisible(self, locator: Locator) -> None:
        """要素が消えるまで待つ（読み込み中の表示が消えるのを待つときなど）。"""
        with self.session._operating(f"wait_invisible({locator})"):
            self._until(EC.invisibility_of_element_located(tuple(locator)), locator, "消え")

    # ------------------------------------------------------------ 警告ダイアログ

    def alert_accept(self) -> None:
        """ブラウザの確認ダイアログで OK を押す。出るまで待つ。"""
        with self.session._operating("alert_accept"):
            self._until(EC.alert_is_present(), "alert", "現れ").accept()

    def alert_dismiss(self) -> None:
        """ブラウザの確認ダイアログでキャンセルを押す。出るまで待つ。"""
        with self.session._operating("alert_dismiss"):
            self._until(EC.alert_is_present(), "alert", "現れ").dismiss()

    def read_alert_text(self) -> str:
        """ブラウザの確認ダイアログの文言を返す。出るまで待つ。"""
        with self.session._operating("read_alert_text"):
            return self._until(EC.alert_is_present(), "alert", "現れ").text

    # ------------------------------------------------------------ 逃げ道

    @contextmanager
    def frame(self, locator: Locator) -> Iterator[Page]:
        """iframe の中を操作し、抜けるときに元の画面へ戻る。

        iframe の中の要素は、切り替えないと見つからない。
        ElementNotFoundError が出て、HTML 上には要素があるのに掴めないときは
        たいていこれが原因:

            with page.frame(page.CONTENT_FRAME):
                page.click(page.SAVE_BUTTON)
            # ← 元の画面へ戻る（中で例外が出ても戻る）

        Yields:
            自分自身。中では今までどおりメソッドを呼べる。
        """
        with self.session._operating(f"frame({locator})"):
            self._until(
                EC.frame_to_be_available_and_switch_to_it(tuple(locator)), locator, "切り替えられ"
            )
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
            return self._until(EC.presence_of_element_located(tuple(locator)), locator, "見つかり")

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
            return self._until(
                EC.presence_of_all_elements_located(tuple(locator)), locator, "見つかり"
            )

    def execute_script(self, script: str, *args: object) -> object:
        """JavaScript を実行して戻り値を返す。

        Args:
            script: 実行する JavaScript。
            *args: スクリプト内で arguments[0], arguments[1] ... として参照できる値。
        """
        with self.session._operating("execute_script"):
            return self.session.raw.execute_script(script, *args)

    # ------------------------------------------------------------ 内部処理

    def _until(self, condition, locator: object, description: str):
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
        return self._until(EC.visibility_of_element_located(tuple(locator)), locator, "表示され")

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(session={self.session.name!r})"


class SitePage(Page):
    """1つのサイト共通の画面クラス。サイトごとにこれを継承する。

    BASE_URL とログインなど、そのサイトのどの画面でも使う処理をここに書く。
    画面ごとのクラスは、さらにこれを継承する:

        Page          … ブラウザ操作（click / input / select ...）
          └ SitePage  … サイト共通（BASE_URL / ログイン / 共通ヘッダー）
              └ LoginPage / HomePage / ...   … 各画面

    BASE_URL は次の順で解決する:
      1. 自身（または親クラス）に `BASE_URL` が定義されていればそれ
      2. 無ければ、`browsers.launch(Site)` で起動した `Site` の `BASE_URL`
    """

    BASE_URL: str = ""

    def go(self, path: str = "") -> Self:
        """BASE_URL からの相対パスへ移動し、自分自身を返す。

        Args:
            path: BASE_URL からの相対パス（例: "/login"）。省略時は BASE_URL を開く。
        """
        self.session.open(self._base_url + path)
        return self

    @property
    def _base_url(self) -> str:
        """画面クラス側の BASE_URL を、なければ Site.BASE_URL から解決する。

        クラス変数の解決は Python の MRO に任せる（`type(self).BASE_URL` ではなく
        `self.__class__.BASE_URL` を使う）。SitePage 側で必ず定義する設計もあるが、
        それでは Site クラスの BASE_URL を取りに行く経路が消えるため、ここでは
        「未設定なら上位 Site を見る」形にしている。
        """
        if self.__class__.BASE_URL:
            return self.__class__.BASE_URL
        site = getattr(self.session, "_site", None)
        if site is not None:
            return site.BASE_URL
        return ""
