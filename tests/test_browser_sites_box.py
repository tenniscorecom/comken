"""Box サイト（comken/toolbox/browser/sites/box/）のテスト。

実ブラウザは起動せず、tests/test_browser_sites_ams.py と同じく WebDriver を
モックする。確かめるのは判断の部分（リンクの href の読み取り・名前の探索・
作成・アップロード・ログインの分岐）だけ。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from selenium.common.exceptions import NoSuchElementException, TimeoutException

from comken.exceptions import BrowserError, LoginFailedError
from comken.toolbox.browser import BrowserOptions, DownloadDir, Locator
from comken.toolbox.browser.management.sessions import BrowserSession
from comken.toolbox.browser.sites.box.pages.app_page import AppPage
from comken.toolbox.browser.sites.box.pages.folder_page import BoxItem, FolderPage
from comken.toolbox.browser.sites.box.pages.login_page import LoginPage
from comken.toolbox.browser.sites.box.site import Box, BoxBrowserOptions

# テストで使う例示用の値（実在のアカウントではない）
TEST_USERNAME = "user@example.com"
TEST_PASSWORD = "secret-password"


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


def _make_driver(elements: dict[tuple[str, str], list[Any]]) -> MagicMock:
    """要素探索だけ本物の Selenium と同じ挙動にする WebDriver の代用。

    ``elements`` は「(by, value) → 要素のリスト」の対応表。テストの途中で
    書き換えると、探索結果も入れ替わる（ログインの2段目のように、
    操作の結果で要素が出現する場面で使う）。
    """
    driver = MagicMock()

    def find_element(by: str, value: str) -> Any:
        found = elements.get((by, value), [])
        if not found:
            raise NoSuchElementException()
        return found[0]

    def find_elements(by: str, value: str) -> list[Any]:
        return list(elements.get((by, value), []))

    driver.find_element.side_effect = find_element
    driver.find_elements.side_effect = find_elements
    driver.current_url = "https://app.box.com/login"
    return driver


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


def _make_login_page(
    tmp_path: Path,
    elements: dict[tuple[str, str], list[Any]],
) -> tuple[LoginPage, MagicMock]:
    """ログイン画面と WebDriver の代用を作る。"""
    driver = _make_driver(elements)
    session = _make_session(tmp_path, driver)
    page = LoginPage(session)
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


class TestLoginPage:
    """LoginPage.login() — ログイン画面の操作。"""

    def test_two_step_login_asks_password_after_next(self, tmp_path):
        """「メール → 次へ → パスワード → ログイン」の順で入力する。"""
        email_input = _mock_element()
        password_input = _mock_element()
        next_button = _mock_element()
        login_button = _mock_element()
        elements: dict[tuple[str, str], list[Any]] = {
            _key(LoginPage.EMAIL_INPUT): [email_input],
            _key(LoginPage.NEXT_BTN): [next_button],
            _key(LoginPage.LOGIN_BTN): [login_button],
        }

        def _on_next() -> None:
            # 「次へ」を押すとパスワード入力欄が出る
            elements[_key(LoginPage.PASSWORD_INPUT)] = [password_input]

        next_button.click.side_effect = _on_next
        page, driver = _make_login_page(tmp_path, elements)

        def _on_login() -> None:
            # ログイン後はログイン画面を離れる（URL が変わる）
            driver.current_url = "https://app.box.com/folder/0"

        login_button.click.side_effect = _on_login

        page.login(TEST_USERNAME, TEST_PASSWORD)

        email_input.send_keys.assert_called_once_with(TEST_USERNAME)
        password_input.send_keys.assert_called_once_with(TEST_PASSWORD)
        next_button.click.assert_called_once()
        login_button.click.assert_called_once()

    def test_single_screen_login_skips_next(self, tmp_path):
        """1画面に両方出る場合は「次へ」を押さない。"""
        email_input = _mock_element()
        password_input = _mock_element()
        next_button = _mock_element()
        login_button = _mock_element()
        elements: dict[tuple[str, str], list[Any]] = {
            _key(LoginPage.EMAIL_INPUT): [email_input],
            _key(LoginPage.PASSWORD_INPUT): [password_input],
            _key(LoginPage.NEXT_BTN): [next_button],
            _key(LoginPage.LOGIN_BTN): [login_button],
        }
        page, driver = _make_login_page(tmp_path, elements)

        def _on_login() -> None:
            # ログイン後はログイン画面を離れる（URL が変わる）
            driver.current_url = "https://app.box.com/folder/0"

        login_button.click.side_effect = _on_login

        page.login(TEST_USERNAME, TEST_PASSWORD)

        next_button.click.assert_not_called()
        email_input.send_keys.assert_called_once_with(TEST_USERNAME)
        password_input.send_keys.assert_called_once_with(TEST_PASSWORD)
        login_button.click.assert_called_once()

    def test_raises_login_failed_when_error_is_shown(self, tmp_path):
        """ログイン画面のエラー表示が出たら LoginFailedError にする。"""
        email_input = _mock_element()
        password_input = _mock_element()
        login_button = _mock_element()
        error_element = _mock_element()
        error_element.text = "パスワードが正しくありません"
        elements: dict[tuple[str, str], list[Any]] = {
            _key(LoginPage.EMAIL_INPUT): [email_input],
            _key(LoginPage.PASSWORD_INPUT): [password_input],
            _key(LoginPage.LOGIN_BTN): [login_button],
            _key(LoginPage.ERROR_MSG): [error_element],
        }
        page, driver = _make_login_page(tmp_path, elements)
        # URL が変わらない（エラーが出たまま）だと、待ちの条件が「エラー表示」になる
        driver.current_url = "https://app.box.com/login"

        with pytest.raises(LoginFailedError, match="パスワードが正しくありません"):
            page.login(TEST_USERNAME, "wrong-password")


class _FakeCredentials:
    """認証情報の代用。"""

    def __init__(self, site: str, path: Path | None = None) -> None:
        self.site = site
        self.username = TEST_USERNAME
        self.password = TEST_PASSWORD


class _HeadlessOptions(BoxBrowserOptions):
    """HEADLESS で起動したときの起動オプション。"""

    HEADLESS = True


class _HeadlessBox(Box):
    """HEADLESS で起動したときの挙動を確かめるためのクラス。"""

    OPTIONS = _HeadlessOptions


class TestBoxLoginWithCredentials:
    """Box.login_with_credentials() — DPAPI の認証情報でログインする。"""

    def test_passes_credentials_to_login_form(self, tmp_path, monkeypatch):
        """DPAPIの認証情報がログイン画面へ渡される。"""
        email_input = _mock_element()
        password_input = _mock_element()
        login_button = _mock_element()
        elements: dict[tuple[str, str], list[Any]] = {
            _key(LoginPage.EMAIL_INPUT): [email_input],
            _key(LoginPage.PASSWORD_INPUT): [password_input],
            _key(LoginPage.LOGIN_BTN): [login_button],
        }
        driver = _make_driver(elements)

        def _on_login() -> None:
            # ログイン後: ログイン画面は消え、アプリの目印（アカウントアイコン）が出る
            elements.pop(_key(LoginPage.EMAIL_INPUT), None)
            elements.pop(_key(LoginPage.PASSWORD_INPUT), None)
            elements[_key(AppPage.APP_SHELL)] = [_mock_element()]
            driver.current_url = "https://app.box.com/folder/0"

        login_button.click.side_effect = _on_login
        session = _make_session(tmp_path, driver)
        box = Box()
        box.session = session
        monkeypatch.setattr("comken.toolbox.credentials.Credentials", _FakeCredentials)

        box.login_with_credentials()

        email_input.send_keys.assert_called_once_with(TEST_USERNAME)
        password_input.send_keys.assert_called_once_with(TEST_PASSWORD)

    def test_uses_class_credential_prefix_by_default(self, tmp_path, monkeypatch):
        """prefix を省略するとクラスの CREDENTIAL_PREFIX が使われる。"""
        elements: dict[tuple[str, str], list[Any]] = {
            _key(AppPage.APP_SHELL): [_mock_element()],
        }
        driver = _make_driver(elements)
        driver.current_url = "https://app.box.com/folder/0"
        session = _make_session(tmp_path, driver)
        box = Box()
        box.session = session
        used: list[str] = []

        class _RecordingCredentials(_FakeCredentials):
            def __init__(self, site: str, path: Path | None = None) -> None:
                used.append(site)
                super().__init__(site, path)

        monkeypatch.setattr("comken.toolbox.credentials.Credentials", _RecordingCredentials)

        box.login_with_credentials()

        assert used == [Box.CREDENTIAL_PREFIX]

    def test_raises_in_headless_when_login_is_not_finished(self, tmp_path, monkeypatch):
        """HEADLESS でログインが済む前は、待たずにエラーにする。"""
        email_input = _mock_element()
        password_input = _mock_element()
        login_button = _mock_element()
        elements: dict[tuple[str, str], list[Any]] = {
            _key(LoginPage.EMAIL_INPUT): [email_input],
            _key(LoginPage.PASSWORD_INPUT): [password_input],
            _key(LoginPage.LOGIN_BTN): [login_button],
        }

        def _on_login() -> None:
            # 送信はできたが、まだログインは済んでいない（2段階認証の画面）
            elements.pop(_key(LoginPage.EMAIL_INPUT), None)
            elements.pop(_key(LoginPage.PASSWORD_INPUT), None)

        login_button.click.side_effect = _on_login
        driver = _make_driver(elements)
        driver.current_url = "https://app.box.com/login"
        session = _make_session(tmp_path, driver)
        box = _HeadlessBox()
        box.session = session
        monkeypatch.setattr("comken.toolbox.credentials.Credentials", _FakeCredentials)

        with pytest.raises(BrowserError, match="HEADLESS"):
            box.login_with_credentials()
