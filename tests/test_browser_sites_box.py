"""Box サイト（comken/toolbox/browser/sites/box/）のテスト。

実ブラウザは起動せず、tests/test_browser_sites_ams.py と同じく WebDriver を
モックする。確かめるのは判断の部分（リンクの href の読み取り・名前の探索・
作成・アップロード・ログインの分岐）だけ。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By

from comken.exceptions import BrowserError, LoginFailedError
from comken.toolbox.browser import BrowserOptions, DownloadDir, Locator
from comken.toolbox.browser.management.sessions import BrowserSession
from comken.toolbox.browser.sites.box.pages.app_page import AppPage
from comken.toolbox.browser.sites.box.pages.folder_page import BoxItem, FolderPage
from comken.toolbox.browser.sites.box.pages.login_page import LoginPage
from comken.toolbox.browser.sites.box.site import Box, BoxBrowserOptions


def _key(locator: Locator) -> tuple[str, str]:
    """セレクターを「(by, value)」の組にする（要素表のキーにするため）。"""
    return (locator.by, locator.value)


class _InstantWait:
    """待たない WebDriverWait の代用。条件は 1 回だけ評価する。

    本物の WebDriverWait は条件が満たされるまで待つため、素の WebDriver を
    モックしたテストでは要素が見つからずにタイムアウトする。ここでは条件を
    1 回だけ評価し、満たさなかったらすぐ TimeoutException にして、
    本物と同じ ``ElementNotFoundError`` として扱えるようにする。
    """

    def __init__(self, driver: Any) -> None:
        self._driver = driver

    def until(self, condition: Callable[[Any], Any], message: str = "") -> Any:
        try:
            value = condition(self._driver)
        except NoSuchElementException as error:
            raise TimeoutException(message) from error
        if not value:
            raise TimeoutException(message)
        return value


def _xpath_literals(value: str) -> list[str]:
    """XPath に含まれる引用符つきの文字列（``'...'``）を抜き出す。"""
    return re.findall(r"'([^']*)'", value)


def _matches_locator(locator: Locator, element: Any) -> bool:
    """要素がセレクターに一致するかを判定する（XPath の表示文字列だけ）。

    XPath で表示文字列を探す場合、「セレクターに書かれた文言」を要素の表示
    文字が含んでいるときだけ一致する。**文言が変わると見つからなくなる**ことを
    確かめるため（表示文字列で探すボタンのテストで使う）。

    表示文字を持たない要素（モックの属性だけを持つ要素）は判定の対象にしない
    （既存のテストを壊さないため）。
    """
    if locator.by != By.XPATH:
        return True
    text = getattr(element, "text", None)
    if not isinstance(text, str):
        return True
    literals = _xpath_literals(locator.value)
    if not literals:
        return True
    return any(literal in text for literal in literals)


def _matching(
    elements: dict[tuple[str, str], list[Any]],
    locator: Locator,
) -> list[Any]:
    """セレクターに一致する要素のリストを返す。"""
    return [
        element
        for element in elements.get((locator.by, locator.value), [])
        if _matches_locator(locator, element)
    ]


def _make_driver(elements: dict[tuple[str, str], list[Any]]) -> MagicMock:
    """要素探索だけ本物の Selenium と同じ挙動にする WebDriver の代用。

    ``elements`` は「(by, value) → 要素のリスト」の対応表。テストの途中で
    書き換えると、探索結果も入れ替わる（ログインの2段目のように、
    操作の結果で要素が出現する場面で使う）。
    """
    driver = MagicMock()

    def find_element(by: str, value: str) -> Any:
        found = _matching(elements, Locator(by, value))
        if not found:
            raise NoSuchElementException()
        return found[0]

    def find_elements(by: str, value: str) -> list[Any]:
        return _matching(elements, Locator(by, value))

    driver.find_element.side_effect = find_element
    driver.find_elements.side_effect = find_elements
    driver.current_url = "https://app.box.com/login"
    return driver


class _FakeClock:
    """待ち時間を進ませる時計の代用（``time`` モジュールの代わりに使う）。

    ``sleep()`` を呼んだ回数を数え、``on_sleep`` で「待っている間に起きること」
    を再現する（Box のログイン完了など）。
    """

    def __init__(self, on_sleep: Callable[[], None] | None = None) -> None:
        self.now = 0.0
        self.sleep_count = 0
        self._on_sleep = on_sleep

    def monotonic(self) -> float:
        """経過時間（秒）を返す。"""
        return self.now

    def sleep(self, seconds: float) -> None:
        """待つ。呼ぶたびに時計を進め、``on_sleep`` を呼ぶ。"""
        self.sleep_count += 1
        self.now += seconds
        if self._on_sleep is not None:
            self._on_sleep()


def _mock_element() -> MagicMock:
    """要素の代用。表示・操作可能の判定が真になるようにする。

    selenium の ``_element_if_visible()`` は ``element.is_displayed() == True``
    と比べるので、判定結果が真の Python の ``True`` を返さないと
    「表示されていない要素」と判定されてしまう。
    """
    element = MagicMock()
    element.is_displayed.return_value = True
    element.is_enabled.return_value = True
    return element


def _element(text: str = "", href: str | None = None) -> MagicMock:
    """要素の代用。表示文字と href を持つ。"""
    element = _mock_element()
    element.text = text
    element.get_attribute.return_value = href
    return element


def _row(*links: MagicMock) -> MagicMock:
    """一覧の1行の代用。行の中のリンクを返す。"""
    row = MagicMock()
    row.find_elements.return_value = list(links)
    return row


def _make_session(tmp_path: Path, driver: MagicMock) -> BrowserSession:
    """モックした WebDriver を持つセッションを作る。"""
    session = BrowserSession(
        name="test",
        options=BrowserOptions(),
        download_dir=DownloadDir(path=tmp_path / "dl"),
        profile_dir=None,
    )
    session._driver = driver
    session._site = Box()
    return session


def _make_folder_page(
    tmp_path: Path,
    elements: dict[tuple[str, str], list[Any]],
) -> tuple[FolderPage, MagicMock]:
    """フォルダ画面と WebDriver の代用を作る。"""
    driver = _make_driver(elements)
    session = _make_session(tmp_path, driver)
    page = FolderPage(session)
    page._wait = _InstantWait(driver)
    return page, driver


def _looked_up(driver: MagicMock) -> list[tuple[str, str]]:
    """探索されたセレクターの一覧（クリックも探索なので含まれる）。"""
    return [call.args for call in driver.find_element.call_args_list]


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """待ち時間を 0 にして、テストが長くならないようにする。"""
    monkeypatch.setattr(
        "comken.toolbox.browser.sites.box.pages.folder_page._POLL_INTERVAL_SECONDS",
        0,
    )


class TestItemReading:
    """items() — 一覧からファイル／フォルダを読み取る。"""

    def test_reads_id_and_kind_from_href(self, tmp_path):
        """ファイルとフォルダのリンクから ID と種類を取り出す。"""
        file_link = _element("報告書.txt", "/file/123")
        folder_link = _element("2026年", "/folder/456")
        elements = {_key(FolderPage.ROWS): [_row(file_link), _row(folder_link)]}
        page, _ = _make_folder_page(tmp_path, elements)

        items = page.items()

        assert items == [
            BoxItem(id="123", name="報告書.txt", kind="file"),
            BoxItem(id="456", name="2026年", kind="folder"),
        ]

    def test_reads_id_from_absolute_url(self, tmp_path):
        """絶対URLの href からも ID を取り出せる。"""
        file_link = _element("報告書.txt", "https://app.box.com/file/789")
        elements = {_key(FolderPage.ROWS): [_row(file_link)]}
        page, _ = _make_folder_page(tmp_path, elements)

        items = page.items()

        assert items == [BoxItem(id="789", name="報告書.txt", kind="file")]

    def test_ignores_links_that_are_not_items(self, tmp_path):
        """Box の項目では無いリンク（/help や /files/0）は無視する。"""
        file_link = _element("報告書.txt", "/file/123")
        help_link = _element("ヘルプ", "/help")
        all_files_link = _element("すべてのファイル", "/files/0")
        elements = {_key(FolderPage.ROWS): [_row(file_link, help_link, all_files_link)]}
        page, _ = _make_folder_page(tmp_path, elements)

        items = page.items()

        assert items == [BoxItem(id="123", name="報告書.txt", kind="file")]

    def test_returns_empty_list_when_folder_has_no_item(self, tmp_path):
        """空のフォルダでは空リストを返す（例外にしない）。"""
        elements = {_key(FolderPage.ROWS): []}
        page, _ = _make_folder_page(tmp_path, elements)

        assert page.items() == []

    def test_reads_items_that_load_while_scrolling(self, tmp_path):
        """遅延読み込みで増えるので、末尾までスクロールして読み切る。"""
        first = _row(_element("1.txt", "/file/1"))
        second = _row(_element("2.txt", "/file/2"))
        elements: dict[tuple[str, str], list[Any]] = {
            _key(FolderPage.ROWS): [first],
        }
        page, driver = _make_folder_page(tmp_path, elements)

        def _on_scroll(script: str, *args: Any) -> None:
            # 末尾までスクロールすると次のページが読み込まれる
            elements[_key(FolderPage.ROWS)] = [first, second]

        driver.execute_script.side_effect = _on_scroll

        items = page.items()

        assert items == [
            BoxItem(id="1", name="1.txt", kind="file"),
            BoxItem(id="2", name="2.txt", kind="file"),
        ]
        assert driver.execute_script.called


class TestFolderPageFind:
    """find() — 名前で項目を探す。"""

    def test_finds_item_by_exact_name(self, tmp_path):
        """完全一致した項目を返す。"""
        file_link = _element("報告書.txt", "/file/123")
        other_link = _element("報告書.csv", "/file/124")
        elements = {_key(FolderPage.ROWS): [_row(file_link), _row(other_link)]}
        page, _ = _make_folder_page(tmp_path, elements)

        found = page.find("報告書.txt")

        assert found == BoxItem(id="123", name="報告書.txt", kind="file")

    def test_returns_none_when_name_is_not_found(self, tmp_path):
        """見つからない場合は None を返す（例外にしない）。"""
        file_link = _element("報告書.txt", "/file/123")
        elements = {_key(FolderPage.ROWS): [_row(file_link)]}
        page, _ = _make_folder_page(tmp_path, elements)

        assert page.find("報告書.csv") is None

    def test_does_not_match_by_partial_name(self, tmp_path):
        """前方一致では拾わない（完全一致だけ）。"""
        file_link = _element("報告書.txt", "/file/123")
        elements = {_key(FolderPage.ROWS): [_row(file_link)]}
        page, _ = _make_folder_page(tmp_path, elements)

        assert page.find("報告書") is None

    def test_raises_when_same_name_appears_twice(self, tmp_path):
        """同名の項目が複数あると、どれを指すか決められないのでエラーにする。"""
        first = _element("報告書.txt", "/file/123")
        second = _element("報告書.txt", "/file/456")
        elements = {_key(FolderPage.ROWS): [_row(first), _row(second)]}
        page, _ = _make_folder_page(tmp_path, elements)

        with pytest.raises(BrowserError, match=r"報告書\.txt"):
            page.find("報告書.txt")


class TestFolderPageCreateFolder:
    """create_folder() — フォルダを作る。"""

    def test_returns_existing_folder_without_creating(self, tmp_path):
        """同名のフォルダが既にあれば、作成操作をせずにそれを返す。"""
        folder_link = _element("2026年", "/folder/456")
        elements = {_key(FolderPage.ROWS): [_row(folder_link)]}
        page, driver = _make_folder_page(tmp_path, elements)

        result = page.create_folder("2026年")

        assert result == BoxItem(id="456", name="2026年", kind="folder")
        looked_up = _looked_up(driver)
        assert _key(FolderPage.NEW_BTN) not in looked_up
        assert _key(FolderPage.CREATE_FOLDER_BTN) not in looked_up

    def test_creates_folder_when_not_found(self, tmp_path):
        """無ければ「新規」からフォルダを作る。"""
        new_button = _mock_element()
        menu_item = _mock_element()
        name_input = _mock_element()
        create_button = _mock_element()
        elements: dict[tuple[str, str], list[Any]] = {
            _key(FolderPage.ROWS): [],
            _key(FolderPage.NEW_BTN): [new_button],
            _key(FolderPage.NEW_FOLDER_MENU_ITEM): [menu_item],
            _key(FolderPage.FOLDER_NAME_INPUT): [name_input],
            _key(FolderPage.CREATE_FOLDER_BTN): [create_button],
        }

        def _on_create() -> None:
            elements[_key(FolderPage.ROWS)] = [_row(_element("新規", "/folder/999"))]

        create_button.click.side_effect = _on_create
        page, driver = _make_folder_page(tmp_path, elements)

        result = page.create_folder("新規")

        assert result == BoxItem(id="999", name="新規", kind="folder")
        name_input.send_keys.assert_called_once_with("新規")
        looked_up = _looked_up(driver)
        assert _key(FolderPage.NEW_BTN) in looked_up
        assert _key(FolderPage.NEW_FOLDER_MENU_ITEM) in looked_up
        assert _key(FolderPage.CREATE_FOLDER_BTN) in looked_up

    def test_raises_when_file_with_same_name_exists(self, tmp_path):
        """同名のファイルが既にあれば、エラーにする（黙って返さない）。"""
        file_link = _element("報告書.txt", "/file/123")
        elements = {_key(FolderPage.ROWS): [_row(file_link)]}
        page, _ = _make_folder_page(tmp_path, elements)

        with pytest.raises(BrowserError, match=r"報告書\.txt"):
            page.create_folder("報告書.txt")


class TestFolderPageUpload:
    """upload() — ファイルをアップロードする。"""

    def test_raises_before_sending_when_file_is_missing(self, tmp_path):
        """ファイルが無いときは、入力欄へ送る前にエラーにする。"""
        elements: dict[tuple[str, str], list[Any]] = {_key(FolderPage.ROWS): []}
        page, driver = _make_folder_page(tmp_path, elements)

        with pytest.raises(BrowserError, match="見つかりません"):
            page.upload(tmp_path / "存在しない.csv")

        # 入力欄へ何も送っていない（要素の探索すらしていない）
        assert driver.find_element.call_args_list == []

    def test_sends_path_to_file_input(self, tmp_path):
        """ファイル入力欄へパスを送る（ファイル選択ダイアログは開かない）。"""
        source = tmp_path / "元データ.csv"
        source.write_text("a,b\n", encoding="utf-8")
        file_input = _mock_element()
        elements: dict[tuple[str, str], list[Any]] = {
            _key(FolderPage.ROWS): [],
            _key(FolderPage.FILE_INPUT): [file_input],
        }

        def _on_send(path: str) -> None:
            elements[_key(FolderPage.ROWS)] = [_row(_element("元データ.csv", "/file/321"))]

        file_input.send_keys.side_effect = _on_send
        page, _ = _make_folder_page(tmp_path, elements)

        result = page.upload(source)

        file_input.send_keys.assert_called_once_with(str(source.resolve()))
        assert result == BoxItem(id="321", name="元データ.csv", kind="file")

    def test_selects_new_version_when_same_name_exists(self, tmp_path):
        """同名ファイルが既にあれば「新しいバージョン」を選ぶ。"""
        source = tmp_path / "報告書.csv"
        source.write_text("a,b\n", encoding="utf-8")
        existing_link = _element("報告書.csv", "/file/123")
        file_input = _mock_element()
        new_version_button = _mock_element()
        elements: dict[tuple[str, str], list[Any]] = {
            _key(FolderPage.ROWS): [_row(existing_link)],
            _key(FolderPage.FILE_INPUT): [file_input],
            _key(FolderPage.UPLOAD_NEW_VERSION_BTN): [new_version_button],
        }
        page, driver = _make_folder_page(tmp_path, elements)

        result = page.upload(source)

        assert result == BoxItem(id="123", name="報告書.csv", kind="file")
        new_version_button.click.assert_called_once()
        assert _key(FolderPage.UPLOAD_NEW_VERSION_BTN) in _looked_up(driver)

    def test_does_not_ask_for_new_version_when_name_is_new(self, tmp_path):
        """同名のファイルが無ければ、確認ダイアログは出さない。"""
        source = tmp_path / "新しい.csv"
        source.write_text("a,b\n", encoding="utf-8")
        file_input = _mock_element()
        new_version_button = _mock_element()
        elements: dict[tuple[str, str], list[Any]] = {
            _key(FolderPage.ROWS): [],
            _key(FolderPage.FILE_INPUT): [file_input],
            _key(FolderPage.UPLOAD_NEW_VERSION_BTN): [new_version_button],
        }

        def _on_send(path: str) -> None:
            elements[_key(FolderPage.ROWS)] = [_row(_element("新しい.csv", "/file/654"))]

        file_input.send_keys.side_effect = _on_send
        page, driver = _make_folder_page(tmp_path, elements)

        page.upload(source)

        new_version_button.click.assert_not_called()
        assert _key(FolderPage.UPLOAD_NEW_VERSION_BTN) not in _looked_up(driver)


class _HeadlessOptions(BoxBrowserOptions):
    """HEADLESS で起動したときの起動オプション。"""

    HEADLESS = True


class _HeadlessBox(Box):
    """HEADLESS で起動したときの挙動を確かめるためのクラス。"""

    OPTIONS = _HeadlessOptions


class TestBoxLogin:
    """Box.login() — 「サインインで続行」を押してログインする。"""

    def test_presses_continue_button_and_waits_until_logged_in(self, tmp_path, monkeypatch):
        """未ログインなら「サインインで続行」を押し、ログイン済みになるまで待つ。"""
        continue_button = _element("サインインで続行")
        elements: dict[tuple[str, str], list[Any]] = {
            _key(LoginPage.CONTINUE_BTN): [continue_button],
        }
        driver = _make_driver(elements)

        def _on_click() -> None:
            # 押した直後はログイン画面を離れるが、アプリはまだ読み込み中
            elements.pop(_key(LoginPage.CONTINUE_BTN), None)
            driver.current_url = "https://app.box.com/folder/0"

        continue_button.click.side_effect = _on_click

        def _on_sleep() -> None:
            # 待っている間にアプリの目印（アカウントアイコン）が現れる
            elements[_key(AppPage.APP_SHELL)] = [_mock_element()]

        clock = _FakeClock(_on_sleep)
        monkeypatch.setattr("comken.toolbox.browser.sites.box.site.time", clock)

        box = Box()
        box.session = _make_session(tmp_path, driver)

        box.login(timeout=60, interval=1)

        continue_button.click.assert_called_once()
        # ログイン済みになるまで待った（1回以上眠っている）
        assert clock.sleep_count >= 1

    def test_does_not_press_button_when_already_logged_in(self, tmp_path):
        """既にログイン済みなら「サインインで続行」を押さない。"""
        elements: dict[tuple[str, str], list[Any]] = {
            _key(AppPage.APP_SHELL): [_mock_element()],
        }
        driver = _make_driver(elements)
        driver.current_url = "https://app.box.com/folder/0"
        box = Box()
        box.session = _make_session(tmp_path, driver)

        box.login(timeout=1, interval=0)

        # ボタンを探すことすらしない
        assert _key(LoginPage.CONTINUE_BTN) not in _looked_up(driver)

    def test_presses_the_button_written_in_japanese(self, tmp_path):
        """「サインインで続行」と書かれたボタンが押される。"""
        other_button = _element("ログイン")
        continue_button = _element("サインインで続行")
        elements: dict[tuple[str, str], list[Any]] = {
            _key(LoginPage.CONTINUE_BTN): [other_button, continue_button],
        }
        driver = _make_driver(elements)

        def _on_click() -> None:
            elements.pop(_key(LoginPage.CONTINUE_BTN), None)
            elements[_key(AppPage.APP_SHELL)] = [_mock_element()]
            driver.current_url = "https://app.box.com/folder/0"

        continue_button.click.side_effect = _on_click
        box = Box()
        box.session = _make_session(tmp_path, driver)

        box.login(timeout=1, interval=0)

        continue_button.click.assert_called_once()
        other_button.click.assert_not_called()

    def test_raises_login_failed_when_error_is_shown(self, tmp_path):
        """ログイン画面のエラー表示が出たら LoginFailedError にする。"""
        continue_button = _element("サインインで続行")
        error_element = _element("パスワードが正しくありません")
        elements: dict[tuple[str, str], list[Any]] = {
            _key(LoginPage.CONTINUE_BTN): [continue_button],
            _key(LoginPage.ERROR_MSG): [error_element],
        }
        driver = _make_driver(elements)
        driver.current_url = "https://app.box.com/login"
        box = Box()
        box.session = _make_session(tmp_path, driver)

        with pytest.raises(LoginFailedError, match="パスワードが正しくありません"):
            box.login(timeout=1, interval=0)

    def test_raises_in_headless_when_login_is_not_finished(self, tmp_path):
        """HEADLESS でログインが済む前は、待たずにエラーにする。"""
        continue_button = _element("サインインで続行")
        elements: dict[tuple[str, str], list[Any]] = {
            _key(LoginPage.CONTINUE_BTN): [continue_button],
        }
        driver = _make_driver(elements)
        box = _HeadlessBox()
        box.session = _make_session(tmp_path, driver)

        with pytest.raises(BrowserError, match="HEADLESS"):
            box.login(timeout=1, interval=0)


class TestBoxIsLoggedIn:
    """Box._is_logged_in() — ログイン済みかどうかの判定。"""

    def test_returns_false_when_continue_button_is_shown(self, tmp_path):
        """「サインインで続行」ボタンが見えていれば、ログイン済みではない。"""
        elements: dict[tuple[str, str], list[Any]] = {
            _key(LoginPage.CONTINUE_BTN): [_element("サインインで続行")],
            _key(AppPage.APP_SHELL): [_mock_element()],
        }
        driver = _make_driver(elements)
        driver.current_url = "https://app.box.com/folder/0"
        box = Box()
        box.session = _make_session(tmp_path, driver)

        assert box._is_logged_in() is False

    def test_returns_false_on_microsoft_account_url(self, tmp_path):
        """Microsoft のアカウント選択画面にいる間は、ログイン済みではない。"""
        elements: dict[tuple[str, str], list[Any]] = {
            _key(AppPage.APP_SHELL): [_mock_element()],
        }
        driver = _make_driver(elements)
        driver.current_url = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
        box = Box()
        box.session = _make_session(tmp_path, driver)

        assert box._is_logged_in() is False

    def test_returns_true_when_app_shell_is_shown(self, tmp_path):
        """目印（アカウントアイコン）があって URL が app.box.com ならログイン済み。"""
        elements: dict[tuple[str, str], list[Any]] = {
            _key(AppPage.APP_SHELL): [_mock_element()],
        }
        driver = _make_driver(elements)
        driver.current_url = "https://app.box.com/folder/0"
        box = Box()
        box.session = _make_session(tmp_path, driver)

        assert box._is_logged_in() is True
