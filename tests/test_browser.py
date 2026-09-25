"""ブラウザ操作のテスト。

実際の Edge は起動せず、WebDriver をモックに差し替えて配線と安全装置だけを確認する。
ブラウザを起動するテストは実行環境（Edge とドライバーのバージョン）に左右され、
CI でも手元でも安定しないため、ここでは扱わない。
"""

import inspect
import os
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from comken.exceptions import BrowserError, ElementNotFoundError
from comken.toolbox import browser
from comken.toolbox.browser import (
    BrowserOptions,
    Browsers,
    BrowserSession,
    DownloadDir,
    Locator,
    Page,
    SiteBase,
    SitePage,
)
from comken.toolbox.browser.management import sessions as sessions_module
from comken.toolbox.browser.management.browsers import Browsers as InternalBrowsers
from comken.toolbox.browser.management.sessions import BrowserSession as InternalBrowserSession
from comken.toolbox.browser.management.startup import _build_driver, create_service


class TestPublicApi:
    """内部整理後も comken.toolbox.browser の公開入口を維持する。"""

    def test_exports_management_classes_from_browser_package(self):
        """管理クラス2つを従来どおり comken.toolbox.browser からimportできる。"""
        assert BrowserSession is InternalBrowserSession
        assert Browsers is InternalBrowsers
        assert {"Browsers", "BrowserSession"} <= set(browser.__all__)


def _make_session(tmp_path, name: str = "test") -> BrowserSession:
    """Edge を起動せずに、起動済みと同じ状態の BrowserSession を作る。"""
    session = BrowserSession(
        name=name,
        options=BrowserOptions(),
        download_dir=DownloadDir(path=tmp_path / f"dl_{name}"),
        profile_dir=None,
    )
    session._driver = MagicMock()
    return session


class TestSessionRequiresWith:
    """with を使わない・使い終わったセッションを弾くことのテスト。"""

    def test_rejects_operation_before_with(self, tmp_path):
        """with に入る前に操作すると BrowserError になる。"""
        session = BrowserSession(
            name="test",
            options=BrowserOptions(),
            download_dir=DownloadDir(path=tmp_path / "dl"),
        )

        with pytest.raises(BrowserError):
            session.open("https://example.com")

    def test_rejects_operation_after_close(self, tmp_path):
        """with を抜けた後に操作すると BrowserError になる。"""
        session = _make_session(tmp_path)
        session.__exit__(None, None, None)

        with pytest.raises(BrowserError):
            session.open("https://example.com")

    def test_quit_failure_still_cleans_download_dir(self, tmp_path):
        """ブラウザの終了に失敗しても、ダウンロードフォルダの後片付けは行われる。"""
        session = _make_session(tmp_path)
        session._driver.quit.side_effect = RuntimeError("quit failed")
        session.download_dir = MagicMock(wraps=session.download_dir)

        with pytest.raises(RuntimeError):
            session.__exit__(None, None, None)

        session.download_dir.__exit__.assert_called_once()
        assert session._is_closed

    def test_temp_download_dir_is_removed_on_exit(self, tmp_path):
        """一時フォルダは with を抜けると実際に削除される。"""
        session = BrowserSession(
            name="test",
            options=BrowserOptions(),
            download_dir=DownloadDir(prefix="comken_test_"),
        )
        session._driver = MagicMock()
        temp_path = session.download_dir.path
        assert temp_path.is_dir()

        session.__exit__(None, None, None)

        assert not temp_path.exists()


class TestSaveScreenshot:
    """save_screenshot の保存先・ファイル名を指定できることのテスト。"""

    def test_defaults_to_logs_dir_with_prefix_name_timestamp(self, tmp_path, monkeypatch):
        """省略時は従来どおり logs/{prefix}_{セッション名}_{日時}.png に保存する。"""
        monkeypatch.setattr(sessions_module, "project_dir", lambda: tmp_path)
        monkeypatch.setattr(
            sessions_module, "now", lambda: datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
        )
        session = _make_session(tmp_path, name="kintai")

        path = session.save_screenshot()

        assert path == tmp_path / "logs" / "screenshot_kintai_20260102_030405.png"
        assert path.parent.is_dir()
        session._driver.save_screenshot.assert_called_once_with(str(path))

    def test_filename_is_used_as_is_without_prefix_or_timestamp(self, tmp_path, monkeypatch):
        """filename を第一引数で渡すと prefix・日時を使わずそのまま logs/ 直下に置く。"""
        monkeypatch.setattr(sessions_module, "project_dir", lambda: tmp_path)
        session = _make_session(tmp_path)

        path = session.save_screenshot("ログイン後.png")

        assert path == tmp_path / "logs" / "ログイン後.png"
        session._driver.save_screenshot.assert_called_once_with(str(path))

    def test_directory_overrides_default_logs_dir(self, tmp_path):
        """directory を指定すると logs/ の代わりにそこへ保存する（自動命名は維持）。"""
        session = _make_session(tmp_path)
        target_dir = tmp_path / "shots"

        path = session.save_screenshot(directory=target_dir)

        assert path.parent == target_dir
        assert path.is_relative_to(target_dir)
        session._driver.save_screenshot.assert_called_once_with(str(path))

    def test_directory_and_filename_together(self, tmp_path):
        """directory と filename を両方指定した場合は両方を使う。"""
        session = _make_session(tmp_path)
        target_dir = tmp_path / "shots"

        path = session.save_screenshot("a.png", directory=target_dir)

        assert path == target_dir / "a.png"
        session._driver.save_screenshot.assert_called_once_with(str(path))

    def test_prefix_still_works_as_keyword_when_filename_is_omitted(self, tmp_path, monkeypatch):
        """directory + prefix を渡すと、カテゴリー分けと従来の自動命名を両立できる。"""
        monkeypatch.setattr(
            sessions_module, "now", lambda: datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
        )
        session = _make_session(tmp_path, name="kintai")
        target_dir = tmp_path / "errors"

        path = session.save_screenshot(directory=target_dir, prefix="error")

        assert path == target_dir / "error_kintai_20260102_030405.png"
        session._driver.save_screenshot.assert_called_once_with(str(path))

    def test_relative_directory_becomes_a_subfolder_of_logs(self, tmp_path, monkeypatch):
        """directory に相対パスを渡すと、カレントディレクトリでなく logs/ のサブフォルダになる。"""
        monkeypatch.setattr(sessions_module, "project_dir", lambda: tmp_path)
        monkeypatch.chdir(tmp_path.parent)  # project_dir() とは別の場所をカレントにする
        session = _make_session(tmp_path)

        path = session.save_screenshot("a.png", directory="errors")

        assert path == tmp_path / "logs" / "errors" / "a.png"
        session._driver.save_screenshot.assert_called_once_with(str(path))

    def test_absolute_directory_escapes_logs_entirely(self, tmp_path, monkeypatch):
        """directory に絶対パスを渡すと logs/ 配下ではなくそこへ直接保存する。"""
        monkeypatch.setattr(sessions_module, "project_dir", lambda: tmp_path / "project")
        session = _make_session(tmp_path)
        elsewhere = tmp_path / "elsewhere"

        path = session.save_screenshot("a.png", directory=elsewhere)

        assert path == elsewhere / "a.png"
        session._driver.save_screenshot.assert_called_once_with(str(path))


class TestSessionStartFailure:
    """起動に失敗したときに、プロセスもフォルダも残さないことのテスト。"""

    def test_quits_driver_when_initialization_fails(self, tmp_path, monkeypatch):
        """起動後の初期化で失敗したら、掴んだブラウザを必ず閉じる。

        ここで閉じ損ねると、誰も参照していない Edge プロセスが残り続ける。
        """
        driver = MagicMock()
        driver.implicitly_wait.side_effect = RuntimeError("初期化に失敗")
        monkeypatch.setattr(
            "comken.toolbox.browser.management.startup.webdriver.Edge", lambda **kwargs: driver
        )

        session = BrowserSession(
            name="test",
            options=BrowserOptions(),
            download_dir=DownloadDir(path=tmp_path / "dl"),
        )

        with pytest.raises(BrowserError):
            session.__enter__()

        driver.quit.assert_called_once_with()

    def test_cleans_download_dir_exactly_once_on_failure(self, tmp_path, monkeypatch):
        """起動に失敗したとき、ダウンロードフォルダの後始末はちょうど1回だけ行う。

        __enter__ が失敗すると with の __exit__ は呼ばれないため、
        後始末は起動処理の側で完結している必要がある。
        """
        monkeypatch.setattr(
            "comken.toolbox.browser.management.startup.webdriver.Edge",
            MagicMock(side_effect=RuntimeError("起動に失敗")),
        )
        download_dir = MagicMock(wraps=DownloadDir(path=tmp_path / "dl"))
        download_dir.path = tmp_path / "dl"

        session = BrowserSession(name="test", options=BrowserOptions(), download_dir=download_dir)

        with pytest.raises(BrowserError):
            session.__enter__()

        download_dir.__exit__.assert_called_once()

    def test_does_not_retry_when_no_source_dir(self, tmp_path, monkeypatch):
        """配布フォルダが未設定なら、ドライバー更新も再試行もしない。"""
        edge = MagicMock(side_effect=RuntimeError("起動に失敗"))
        monkeypatch.setattr("comken.toolbox.browser.management.startup.webdriver.Edge", edge)

        session = BrowserSession(
            name="test",
            options=BrowserOptions(),
            download_dir=DownloadDir(path=tmp_path / "dl"),
        )

        with pytest.raises(BrowserError):
            session.__enter__()

        assert edge.call_count == 1


class TestDriverPathResolution:
    """DRIVER_PATH が相対パスでも、Service には絶対パスで渡ることの確認。

    相対パスのまま Service(executable_path=...) へ渡すと、実行時の
    カレントディレクトリ次第で見つからなくなる（PROFILE_ROOT と同じ理由の
    回帰防止）。
    """

    def test_resolves_relative_driver_path_to_absolute(self, tmp_path, monkeypatch):
        service_class = MagicMock(return_value=MagicMock())
        edge = MagicMock(return_value=MagicMock())
        monkeypatch.setattr("comken.toolbox.browser.management.startup.Service", service_class)
        monkeypatch.setattr("comken.toolbox.browser.management.startup.webdriver.Edge", edge)
        monkeypatch.chdir(tmp_path)

        class RelativeDriverOptions(BrowserOptions):
            DRIVER_PATH = "./msedgedriver.exe"

        session = BrowserSession(
            name="test",
            options=RelativeDriverOptions(),
            download_dir=DownloadDir(path=tmp_path / "dl"),
        )
        session.__enter__()

        called_path = service_class.call_args.kwargs["executable_path"]
        assert Path(called_path).is_absolute()
        assert Path(called_path) == (tmp_path / "msedgedriver.exe").resolve()


class TestExternalLogSuppression:
    """ドライバーと Edge 自身の標準出力を抑える設定のテスト。"""

    def test_suppresses_driver_and_edge_logs_by_default(self, tmp_path, monkeypatch):
        """既定では新しい Selenium の Service と Edge の両方へ抑制設定を渡す。"""
        service = MagicMock()
        service_class = MagicMock(return_value=service)
        service_class.__signature__ = inspect.Signature(
            parameters=[
                inspect.Parameter("executable_path", inspect.Parameter.POSITIONAL_OR_KEYWORD),
                inspect.Parameter("log_output", inspect.Parameter.KEYWORD_ONLY),
            ]
        )
        edge = MagicMock(return_value=MagicMock())
        monkeypatch.setattr("comken.toolbox.browser.management.startup.Service", service_class)
        monkeypatch.setattr("comken.toolbox.browser.management.startup.webdriver.Edge", edge)
        session = BrowserSession(
            name="test",
            options=BrowserOptions(),
            download_dir=DownloadDir(path=tmp_path / "dl"),
        )

        _build_driver(tmp_path / "msedgedriver.exe", session._options, None, session.download_dir)

        service_class.assert_called_once_with(
            executable_path=str(tmp_path / "msedgedriver.exe"), log_output=os.devnull
        )
        edge_options = edge.call_args.kwargs["options"]
        assert "--log-level=3" in edge_options.arguments
        assert edge_options.experimental_options["excludeSwitches"] == ["enable-logging"]

    def test_uses_log_path_with_old_selenium(self, tmp_path, monkeypatch):
        """古い Selenium では TypeError を避けるため旧引数 log_path を使う。"""
        calls = []

        class OldService:
            def __init__(self, executable_path, log_path=None):
                calls.append((executable_path, log_path))

        monkeypatch.setattr("comken.toolbox.browser.management.startup.Service", OldService)

        create_service(tmp_path / "msedgedriver.exe", suppress_logs=True)

        assert calls == [(str(tmp_path / "msedgedriver.exe"), os.devnull)]

    def test_can_restore_external_logs(self, tmp_path, monkeypatch):
        """調査時はオプション1つでドライバーと Edge のログ抑制を外せる。"""

        class DebugOptions(BrowserOptions):
            SUPPRESS_EXTERNAL_LOGS = False

        service = MagicMock()
        service_class = MagicMock(return_value=service)
        edge = MagicMock(return_value=MagicMock())
        monkeypatch.setattr("comken.toolbox.browser.management.startup.Service", service_class)
        monkeypatch.setattr("comken.toolbox.browser.management.startup.webdriver.Edge", edge)
        session = BrowserSession(
            name="test",
            options=DebugOptions(),
            download_dir=DownloadDir(path=tmp_path / "dl"),
        )

        _build_driver(tmp_path / "msedgedriver.exe", session._options, None, session.download_dir)

        service_class.assert_called_once_with(executable_path=str(tmp_path / "msedgedriver.exe"))
        edge_options = edge.call_args.kwargs["options"]
        assert "--log-level=3" not in edge_options.arguments
        assert "excludeSwitches" not in edge_options.experimental_options


class TestPopupTab:
    """別タブの操作と後始末のテスト。"""

    def test_closes_tab_and_returns_to_original(self, tmp_path):
        """別タブを閉じて、元のタブへ戻る。"""
        session = _make_session(tmp_path)
        driver = session._driver
        driver.current_window_handle = "main"
        driver.window_handles = ["main", "popup"]

        with session.popup_tab():
            pass

        driver.close.assert_called_once_with()
        assert driver.switch_to.window.call_args_list[-1].args == ("main",)

    def test_cleanup_failure_does_not_hide_original_error(self, tmp_path):
        """後始末に失敗しても、中で起きた本来のエラーを覆い隠さない。"""
        session = _make_session(tmp_path)
        driver = session._driver
        driver.current_window_handle = "main"
        driver.window_handles = ["main", "popup"]
        driver.close.side_effect = RuntimeError("タブを閉じられない")

        with pytest.raises(ValueError, match="本来のエラー"), session.popup_tab():
            raise ValueError("本来のエラー")

    def test_skips_close_when_tab_closed_itself(self, tmp_path):
        """ページ側がタブを閉じていた場合は、閉じ直そうとしない。"""
        session = _make_session(tmp_path)
        driver = session._driver
        driver.current_window_handle = "main"
        # with に入るときは2枚、抜けるときは popup が自分で閉じている
        handles = iter([["main", "popup"], ["main", "popup"], ["main"], ["main"]])
        type(driver).window_handles = property(lambda self: next(handles))

        try:
            with session.popup_tab():
                pass

            driver.close.assert_not_called()
        finally:
            del type(driver).window_handles

    def test_raises_when_no_new_tab(self, tmp_path):
        """新しいタブが開かなければ BrowserError になる。"""
        session = _make_session(tmp_path)
        driver = session._driver
        driver.current_window_handle = "main"
        driver.window_handles = ["main"]

        with pytest.raises(BrowserError), session.popup_tab(timeout=1):
            pass


class TestBrowsersRequiresWith:
    """with を使わない書き方を弾くことのテスト。"""

    def test_rejects_launch_without_with(self, monkeypatch):
        """with に入れずに launch すると、ブラウザを起動する前に止まる。"""
        edge = MagicMock()
        monkeypatch.setattr("comken.toolbox.browser.management.startup.webdriver.Edge", edge)

        browsers = Browsers()

        with pytest.raises(BrowserError):
            browsers.launch_session("kintai")

        edge.assert_not_called()  # 弾かれた時点で何も起きていない

    def test_rejects_getitem_without_with(self):
        """with に入れずにセッションを取り出すこともできない。"""
        browsers = Browsers()

        with pytest.raises(BrowserError):
            browsers["kintai"]

    def test_rejects_launch_after_with(self, monkeypatch):
        """with を抜けた後に使うと BrowserError になる。"""
        monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
        monkeypatch.setattr(BrowserSession, "__exit__", lambda self, *args: None)

        with Browsers() as browsers:
            browsers.launch_session("kintai")

        with pytest.raises(BrowserError):
            browsers.launch_session("keiri")

    def test_error_message_shows_correct_form(self):
        """エラーメッセージに、正しい書き方が載っている。"""
        browsers = Browsers()

        with pytest.raises(BrowserError) as exc_info:
            browsers.launch_session("kintai")

        assert "with Browsers() as browsers:" in str(exc_info.value)


class TestBrowsers:
    """複数サイトのまとめ管理のテスト。"""

    def test_rejects_duplicate_name(self, tmp_path, monkeypatch):
        """同じ名前で2回起動すると BrowserError になる。"""
        monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
        monkeypatch.setattr(BrowserSession, "__exit__", lambda self, *args: None)

        with Browsers() as browsers:
            browsers.launch_session("kintai")
            with pytest.raises(BrowserError):
                browsers.launch_session("kintai")

    def test_getitem_reports_launched_names(self, tmp_path, monkeypatch):
        """未起動の名前を取り出すと、起動済みの一覧つきで BrowserError になる。"""
        monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
        monkeypatch.setattr(BrowserSession, "__exit__", lambda self, *args: None)

        with Browsers() as browsers:
            browsers.launch_session("kintai")

            assert browsers.names == ["kintai"]
            with pytest.raises(BrowserError) as exc_info:
                browsers["keiri"]
            assert "kintai" in str(exc_info.value)

    def test_download_dir_is_separated_per_session(self, tmp_path, monkeypatch):
        """DOWNLOAD_DIR を共有しても、セッション名ごとのサブフォルダに分かれる。"""
        monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
        monkeypatch.setattr(BrowserSession, "__exit__", lambda self, *args: None)

        class SharedOptions(BrowserOptions):
            DOWNLOAD_DIR = str(tmp_path / "downloads")

        with Browsers() as browsers:
            kintai = browsers.launch_session("kintai", SharedOptions)
            keiri = browsers.launch_session("keiri", SharedOptions)

            assert kintai.download_dir.path != keiri.download_dir.path
            assert kintai.download_dir.path.name == "kintai"
            assert keiri.download_dir.path.name == "keiri"

    def test_options_class_is_instantiated_per_session(self, tmp_path, monkeypatch):
        """オプションをクラスで渡すと、セッションごとに別インスタンスになる。"""
        monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
        monkeypatch.setattr(BrowserSession, "__exit__", lambda self, *args: None)

        with Browsers() as browsers:
            kintai = browsers.launch_session("kintai", BrowserOptions)
            keiri = browsers.launch_session("keiri", BrowserOptions)

            assert kintai._options is not keiri._options

    def test_closes_all_sessions_on_error(self, tmp_path, monkeypatch):
        """途中で例外が出ても、起動済みのセッションはすべて閉じられる。"""
        closed = []
        monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
        monkeypatch.setattr(
            BrowserSession, "__exit__", lambda self, *args: closed.append(self.name)
        )

        with pytest.raises(RuntimeError), Browsers() as browsers:
            browsers.launch_session("kintai")
            browsers.launch_session("keiri")
            raise RuntimeError("処理中のエラー")

        # ExitStack は起動と逆順に閉じる
        assert closed == ["keiri", "kintai"]


class TestOptionsBuild:
    """起動オプションの組み立てのテスト。"""

    def test_incognito_by_default(self):
        """既定ではシークレットモードで起動する。"""
        args = BrowserOptions().build()

        assert "--incognito" in args
        assert not any(a.startswith("--user-data-dir=") for a in args)

    def test_profile_dir_disables_incognito(self, tmp_path):
        """プロファイルを指定すると、シークレットモードは自動的に外れる。"""
        args = BrowserOptions().build(profile_dir=tmp_path)

        assert "--incognito" not in args
        assert f"--user-data-dir={tmp_path}" in args

    def test_value_args_are_skipped_when_none(self):
        """値が None の項目は引数に出ない。"""
        args = BrowserOptions().build()

        assert not any(a.startswith("--user-agent=") for a in args)


class TestRemovedNames:
    """作り直しで無くなった名前を使ったときの案内のテスト。"""

    def test_unknown_name_raises_plain_error(self):
        """それ以外の未知の名前は、普通の AttributeError になる。"""
        import comken.toolbox.browser as browser_package

        with pytest.raises(AttributeError, match="has no attribute"):
            _ = browser_package.NotAThing


class TestLocator:
    """セレクターの宣言的管理のテスト。"""

    def test_factories_build_correct_by(self):
        """各ファクトリが正しい By 種別を持つ。"""
        assert Locator.id("x") == (By.ID, "x")
        assert Locator.name("x") == (By.NAME, "x")
        assert Locator.css(".x") == (By.CSS_SELECTOR, ".x")
        assert Locator.link_text("x") == (By.LINK_TEXT, "x")
        assert Locator.partial_link_text("x") == (By.PARTIAL_LINK_TEXT, "x")
        assert Locator.xpath("//x") == (By.XPATH, "//x")

    def test_unpacks_into_selenium_call(self):
        """find_element(*locator) の形でそのまま展開できる。"""
        by, value = Locator.css("#login-btn")

        assert (by, value) == (By.CSS_SELECTOR, "#login-btn")


class TestPage:
    """画面操作の配線とエラー変換のテスト。"""

    def _page(self, tmp_path) -> Page:
        page = Page(_make_session(tmp_path))
        page._wait = MagicMock()
        return page

    def test_click_uses_waited_element(self, tmp_path):
        """click は待機して得た要素をクリックする。"""
        page = self._page(tmp_path)

        page.click(Locator.id("login-btn"))

        page._wait.until.return_value.click.assert_called_once_with()

    def test_input_clears_before_typing(self, tmp_path):
        """input は既存の値を消してから入力する。"""
        page = self._page(tmp_path)

        page.input(Locator.name("username"), "yamada")

        element = page._wait.until.return_value
        element.clear.assert_called_once_with()
        element.send_keys.assert_called_once_with("yamada")

    def test_count_uses_find_elements(self, tmp_path):
        """count は待たずにその場で数える。"""
        page = self._page(tmp_path)
        page.session._driver.find_elements.return_value = [1, 2, 3]

        assert page.count_elements(Locator.css("table tr")) == 3
        page.session._driver.find_elements.assert_called_with(By.CSS_SELECTOR, "table tr")

    def test_timeout_becomes_element_not_found_with_selector(self, tmp_path):
        """時間切れは、どのセレクターで失敗したかが分かる例外に変わる。"""
        page = self._page(tmp_path)
        page._wait.until.side_effect = TimeoutException()

        with pytest.raises(ElementNotFoundError) as exc_info:
            page.click(Locator.id("login-btn"))

        assert "login-btn" in str(exc_info.value)

    def test_elements_returns_all_matches(self, tmp_path):
        """elements は一致した全要素をリストで返す。"""
        page = self._page(tmp_path)
        rows = [MagicMock(), MagicMock(), MagicMock()]
        page._wait.until.return_value = rows

        assert page.find_elements(Locator.css("table tr")) == rows

    def test_elements_reports_selector_when_none_found(self, tmp_path):
        """1件も見つからなければ、セレクター付きのエラーになる。"""
        page = self._page(tmp_path)
        page._wait.until.side_effect = TimeoutException()

        with pytest.raises(ElementNotFoundError) as exc_info:
            page.find_elements(Locator.css("table tr"))

        assert "table tr" in str(exc_info.value)

    def test_frame_returns_to_default_content_on_error(self, tmp_path):
        """iframe の中で例外が出ても、元の画面へ戻る。"""
        page = self._page(tmp_path)

        with pytest.raises(RuntimeError), page.frame(Locator.id("content")):
            raise RuntimeError("中での失敗")

        page.session._driver.switch_to.default_content.assert_called_once_with()

    def test_click_if_present_clicks_when_element_exists(self, tmp_path):
        """要素があればクリックし、True を返す。"""
        page = self._page(tmp_path)

        result = page.click_if_present(Locator.id("login-btn"))

        assert result is True
        page._wait.until.return_value.click.assert_called_once_with()

    def test_click_if_present_skips_when_element_missing(self, tmp_path):
        """要素が無ければクリックせず、False を返す。"""
        page = self._page(tmp_path)
        page.session._driver.find_element.side_effect = NoSuchElementException()

        result = page.click_if_present(Locator.id("login-btn"))

        assert result is False
        page._wait.until.assert_not_called()

    def test_raise_if_shown_raises_with_displayed_text(self, tmp_path):
        """要素があれば、表示文字を渡して作った例外を送出する。"""
        page = self._page(tmp_path)
        page._wait.until.return_value.text = "エラーが発生しました"

        with pytest.raises(ValueError, match="エラーが発生しました"):
            page.raise_if_shown(Locator.css(".error"), ValueError)

    def test_raise_if_shown_does_nothing_when_not_shown(self, tmp_path):
        """要素が無ければ何もしない。"""
        page = self._page(tmp_path)
        page.session._driver.find_element.side_effect = NoSuchElementException()

        page.raise_if_shown(Locator.css(".error"), ValueError)  # 例外が出なければ OK

    def test_raise_if_shown_does_nothing_when_text_is_empty(self, tmp_path):
        """要素はあっても表示文字が空なら、まだ出ていない扱いで何もしない。"""
        page = self._page(tmp_path)
        page._wait.until.return_value.text = ""

        page.raise_if_shown(Locator.css(".error"), ValueError)  # 例外が出なければ OK

    def test_wait_for_result_waits_on_url_change_or_error(self, tmp_path):
        """URL の変化かエラー表示のどちらかを待つ条件を組み立てて待機する。"""
        page = self._page(tmp_path)

        page.wait_for_result("https://example.com/login", Locator.css(".error"))

        page._wait.until.assert_called_once()

    def test_wait_for_result_timeout_becomes_element_not_found(self, tmp_path):
        """時間切れは、どのセレクターで失敗したかが分かる例外に変わる。"""
        page = self._page(tmp_path)
        page._wait.until.side_effect = TimeoutException()

        with pytest.raises(ElementNotFoundError) as exc_info:
            page.wait_for_result("https://example.com/login", Locator.css(".error"))

        assert ".error" in str(exc_info.value)

    def test_wait_for_result_catches_error_that_appears_after_a_short_async_delay(self, tmp_path):
        """エラー表示が非同期で少し遅れて出ても、一度きりの確認では見逃さず、
        URLが変わるかエラーが出るまで待ってから正しく検知する（レースコンディションの
        回帰確認。このテストだけ _wait を完全モックにせず、短いポーリング間隔の実物に
        差し替えて実際の待機ロジックを検証する。wait_for_result() 自体の挙動なので、
        呼び出し側のサイトごとに複製しない — ここ1箇所で確認する）。
        """
        page = self._page(tmp_path)
        page._wait = WebDriverWait(page.session.raw, timeout=1, poll_frequency=0.05)
        page.session._driver.current_url = "https://example.com/login"
        error_locator = Locator.css(".error")

        # error_locator だけ最初の数回は見つからない（＝非同期で少し遅れて出る）
        # ことにする
        lookup_count = 0

        def find_element_side_effect(by, value):
            nonlocal lookup_count
            if (by, value) != tuple(error_locator):
                return MagicMock()
            lookup_count += 1
            if lookup_count < 3:
                raise NoSuchElementException()
            return MagicMock()

        page.session._driver.find_element.side_effect = find_element_side_effect

        # 例外なく確定すれば検知できている
        page.wait_for_result("https://example.com/login", error_locator)

        assert lookup_count >= 3  # 最初の数回は見つからなかった（＝遅延を実際に待った）

    def test_wait_for_result_ignores_error_element_with_empty_text(self, tmp_path):
        """エラー要素が最初から空文字でDOMに在っても、実際に文字が入るまでは
        確定しない（raise_if_shown() の「文字が空ならまだ出ていない」判定と
        合わせた回帰確認。要素の有無だけで判定すると、空のコンテナが最初から
        DOMに在る画面で即座に誤確定してしまう）。
        """
        page = self._page(tmp_path)
        page._wait = WebDriverWait(page.session.raw, timeout=1, poll_frequency=0.05)
        page.session._driver.current_url = "https://example.com/login"
        error_locator = Locator.css(".error")

        lookup_count = 0
        error_element = MagicMock()
        error_element.text = ""

        def find_element_side_effect(by, value):
            nonlocal lookup_count
            if (by, value) != tuple(error_locator):
                return MagicMock()
            lookup_count += 1
            if lookup_count >= 3:
                error_element.text = "エラーが発生しました"
            return error_element

        page.session._driver.find_element.side_effect = find_element_side_effect

        page.wait_for_result("https://example.com/login", error_locator)

        assert lookup_count >= 3  # 空文字の間は確定せず、実際に文字が入るまで待った

    def test_wait_until_any_waits_for_first_true_condition(self, tmp_path):
        """複数の条件のうち、どれか一つが真になるまで待つ。"""
        page = self._page(tmp_path)

        page.wait_until_any(page.url_changed("https://example.com/login"))

        page._wait.until.assert_called_once()

    def test_wait_until_any_timeout_becomes_element_not_found(self, tmp_path):
        """時間切れは ElementNotFoundError になる。"""
        page = self._page(tmp_path)
        page._wait.until.side_effect = TimeoutException()

        with pytest.raises(ElementNotFoundError):
            page.wait_until_any(page.url_changed("https://example.com/login"))

    def test_wait_for_url_change_waits_until_url_differs_from_entry(self, tmp_path):
        """with に入った時点のURLを基準に、抜けた後に実際に変わるまで待つ。"""
        page = self._page(tmp_path)
        page._wait = WebDriverWait(page.session.raw, timeout=1, poll_frequency=0.05)
        page.session._driver.current_url = "https://example.com/login"

        with page.wait_for_url_change():
            page.session._driver.current_url = "https://example.com/home"

        # ここまで例外なく進めば、with を抜けた後のURLで確定できている

    def test_wait_for_url_change_times_out_when_url_stays_the_same(self, tmp_path):
        """with を抜けてもURLが変わらなければタイムアウトになる。"""
        page = self._page(tmp_path)
        page._wait = WebDriverWait(page.session.raw, timeout=0.2, poll_frequency=0.05)
        page.session._driver.current_url = "https://example.com/login"

        with pytest.raises(ElementNotFoundError), page.wait_for_url_change():
            pass  # URLを変えない


class TestSitePage:
    """サイト共通の画面クラスのテスト。"""

    def test_go_joins_base_url(self, tmp_path):
        """go は BASE_URL と相対パスをつないで開く。"""

        class KintaiPage(SitePage):
            BASE_URL = "https://kintai.example.co.jp"

        page = KintaiPage(_make_session(tmp_path))

        result = page.go("/login")

        page.session._driver.get.assert_called_once_with("https://kintai.example.co.jp/login")
        assert result is page

    def test_go_falls_back_to_site_base_url(self, tmp_path):
        """SitePage 側に BASE_URL が無ければ、SiteBase.BASE_URL が使われる。"""

        class KintaiPage(SitePage):
            # BASE_URL は SiteBase 側だけで持ち、SitePage には書かない
            pass

        session = _make_session(tmp_path)
        session._site = SiteBase.__new__(SiteBase)
        session._site.NAME = "kintai"
        session._site.BASE_URL = "https://kintai.example.co.jp"
        session._site.OPTIONS = None

        page = KintaiPage(session)
        page.go("/login")

        page.session._driver.get.assert_called_once_with("https://kintai.example.co.jp/login")

    def test_site_base_url_takes_precedence_over_own(self, tmp_path):
        """SitePage.BASE_URL が設定されていれば、それが SiteBase よりも優先される。"""

        class KintaiPage(SitePage):
            BASE_URL = "https://kintai.example.co.jp/page"

        session = _make_session(tmp_path)
        session._site = SiteBase.__new__(SiteBase)
        session._site.NAME = "kintai"
        session._site.BASE_URL = "https://other.example.co.jp"
        session._site.OPTIONS = None

        page = KintaiPage(session)
        page.go("/login")

        page.session._driver.get.assert_called_once_with("https://kintai.example.co.jp/page/login")


class TestBrowsersLaunchSite:
    """`Browsers.launch(SiteBase)` の挙動のテスト。"""

    def test_returns_site_instance_with_session(self, tmp_path, monkeypatch):
        """launch(SiteBase) はそのインスタンスを返し、.session から BrowserSession に繋がる。"""
        monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
        monkeypatch.setattr(BrowserSession, "__exit__", lambda self, *args: None)

        class KintaiOptions(BrowserOptions):
            pass

        class Kintai(SiteBase):
            NAME = "kintai"
            BASE_URL = "https://kintai.example.co.jp"
            OPTIONS = KintaiOptions
            OWNER = "test_browser / テスト"

        with Browsers() as browsers:
            kintai = browsers.launch(Kintai)

            assert isinstance(kintai, Kintai)
            assert kintai.NAME == "kintai"
            assert kintai.BASE_URL == "https://kintai.example.co.jp"
            assert isinstance(kintai.session, BrowserSession)
            assert kintai.session.name == "kintai"
            assert kintai.session._site is kintai

    def test_uses_site_name_as_session_name(self, tmp_path, monkeypatch):
        """SiteBase.NAME がそのままセッション名として使われる。"""
        monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
        monkeypatch.setattr(BrowserSession, "__exit__", lambda self, *args: None)

        class Kintai(SiteBase):
            NAME = "kintai"
            OPTIONS = BrowserOptions
            OWNER = "test_browser / テスト"

        with Browsers() as browsers:
            kintai = browsers.launch(Kintai)

            assert kintai.session.name == "kintai"
            assert browsers.names == ["kintai"]

    def test_uses_site_options_as_launch_options(self, tmp_path, monkeypatch):
        """SiteBase.OPTIONS が起動オプションとして渡る（launch_session() 経由）。"""

        class KintaiOptions(BrowserOptions):
            WAIT_SECONDS = 20

        class Kintai(SiteBase):
            NAME = "kintai"
            OPTIONS = KintaiOptions
            OWNER = "test_browser / テスト"

        # ``BrowserSession.__enter__`` の ``options`` は ``BrowserOptions | None``。
        # テストでは None もそのまま記録して launch_session へ転送する。
        captured: list[BrowserOptions | None] = []

        real_resolve = InternalBrowsers.launch_session

        def capture(self, name, options: BrowserOptions | None = None, download_dir=None):
            captured.append(options)
            return real_resolve(self, name, options, download_dir)

        monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
        monkeypatch.setattr(BrowserSession, "__exit__", lambda self, *args: None)
        monkeypatch.setattr(InternalBrowsers, "launch_session", capture)

        with Browsers() as browsers:
            browsers.launch(Kintai)

        assert len(captured) == 1
        # launch_session() にはクラスのまま渡る（インスタンス化は _resolve_options が担当）
        assert captured[0] is KintaiOptions

    def test_rejects_site_without_name(self, monkeypatch):
        """NAME が空の SiteBase サブクラスを渡すと BrowserError で止まる。"""

        class Unnamed(SiteBase):
            BASE_URL = "https://example.co.jp"
            OPTIONS = BrowserOptions

        monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
        monkeypatch.setattr(BrowserSession, "__exit__", lambda self, *args: None)

        with Browsers() as browsers, pytest.raises(BrowserError) as exc_info:
            browsers.launch(Unnamed)

        assert "Unnamed" in str(exc_info.value)
        assert "NAME" in str(exc_info.value)

    def test_rejects_launch_without_with(self, monkeypatch):
        """with に入れずに launch(SiteBase) すると、ブラウザを起動する前に止まる。"""
        edge = MagicMock()
        monkeypatch.setattr("comken.toolbox.browser.management.startup.webdriver.Edge", edge)

        class Kintai(SiteBase):
            NAME = "kintai"
            OPTIONS = BrowserOptions
            OWNER = "test_browser / テスト"

        browsers = Browsers()

        with pytest.raises(BrowserError):
            browsers.launch(Kintai)

        edge.assert_not_called()  # 弾かれた時点で何も起きていない

    def test_rejects_duplicate_site_name(self, tmp_path, monkeypatch):
        """同じ NAME の SiteBase を2回起動すると BrowserError になる。"""
        monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
        monkeypatch.setattr(BrowserSession, "__exit__", lambda self, *args: None)

        class Kintai(SiteBase):
            NAME = "kintai"
            OPTIONS = BrowserOptions
            OWNER = "test_browser / テスト"

        with Browsers() as browsers:
            browsers.launch(Kintai)
            with pytest.raises(BrowserError):
                browsers.launch(Kintai)


class TestResolveProfileDir:
    """PROFILE_ROOT の解決（_resolve_profile_dir）— 相対パスでも絶対パスへ直す。

    相対パスのまま --user-data-dir に渡すと、msedge.exe 側の作業ディレクトリ
    次第でプロファイル初期化に失敗し、紛らわしいバージョン不一致メッセージで
    BrowserError になる回帰の再発防止。
    """

    def test_resolves_relative_profile_root_to_absolute(self, tmp_path, monkeypatch):
        monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
        monkeypatch.setattr(BrowserSession, "__exit__", lambda self, *args: None)
        monkeypatch.chdir(tmp_path)

        class RelativeProfileOptions(BrowserOptions):
            PROFILE_ROOT = "./test"

        with Browsers() as browsers:
            session = browsers.launch_session("kintai", RelativeProfileOptions)

        assert session._profile_dir is not None
        assert session._profile_dir.is_absolute()
        assert session._profile_dir == (tmp_path / "test" / "kintai").resolve()

    def test_leaves_absolute_profile_root_unchanged(self, tmp_path, monkeypatch):
        monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
        monkeypatch.setattr(BrowserSession, "__exit__", lambda self, *args: None)

        class AbsoluteProfileOptions(BrowserOptions):
            PROFILE_ROOT = str(tmp_path / "profiles")

        with Browsers() as browsers:
            session = browsers.launch_session("kintai", AbsoluteProfileOptions)

        assert session._profile_dir == tmp_path / "profiles" / "kintai"

    def test_none_when_profile_root_unset(self, monkeypatch):
        monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
        monkeypatch.setattr(BrowserSession, "__exit__", lambda self, *args: None)

        with Browsers() as browsers:
            session = browsers.launch_session("kintai", BrowserOptions)

        assert session._profile_dir is None


class TestBrowsersLaunchSession:
    """`Browsers.launch_session(name, options)`（低レベル経路）のテスト。"""

    def test_returns_browser_session(self, tmp_path, monkeypatch):
        """launch_session() は従来どおり BrowserSession を返す。"""
        monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
        monkeypatch.setattr(BrowserSession, "__exit__", lambda self, *args: None)

        with Browsers() as browsers:
            session = browsers.launch_session("kintai", BrowserOptions)

            assert isinstance(session, BrowserSession)
            assert session.name == "kintai"

    def test_rejects_launch_session_without_with(self, monkeypatch):
        """with に入れずに launch_session しても動かない。"""
        edge = MagicMock()
        monkeypatch.setattr("comken.toolbox.browser.management.startup.webdriver.Edge", edge)

        browsers = Browsers()

        with pytest.raises(BrowserError):
            browsers.launch_session("kintai")

        edge.assert_not_called()


class TestSiteStandsAlone:
    """SiteBase を単体で使える（Browsers を経由しない）ことを固める。

    1サイトだけ触るツールで `with Browsers() as browsers:` を挟ませたくない。
    Salesforce の `with Solution() as sf:` と同じ形で始められるようにする。
    """

    @staticmethod
    def _no_real_browser(monkeypatch):
        """BrowserSession の起動・終了だけ差し替える（既存テストと同じやり方）。"""
        closed = []
        monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
        monkeypatch.setattr(BrowserSession, "__exit__", lambda self, *a: closed.append(self))
        return closed

    def test_creates_its_own_browser_when_session_is_omitted(self, monkeypatch):
        """session を省略すると、自分でブラウザを起動する。"""
        self._no_real_browser(monkeypatch)

        class Kintai(SiteBase):
            NAME = "kintai"
            BASE_URL = "https://kintai.example.co.jp"
            OWNER = "test_browser / テスト"

        with Kintai() as kintai:
            assert isinstance(kintai.session, BrowserSession)
            assert kintai.BASE_URL == "https://kintai.example.co.jp"

    def test_closes_the_browser_it_started(self, monkeypatch):
        """自分で起動したブラウザは、with を抜けるときに閉じる。"""
        closed = self._no_real_browser(monkeypatch)

        class Kintai(SiteBase):
            NAME = "kintai"
            OWNER = "test_browser / テスト"

        with Kintai():
            assert not closed, "with の中で閉じてしまっている"

        assert closed, "自分で起動したブラウザを閉じていない"

    def test_does_not_close_a_session_it_was_given(self, monkeypatch):
        """Browsers から渡されたセッションは閉じない（持ち主は Browsers）。"""
        closed = self._no_real_browser(monkeypatch)

        class Kintai(SiteBase):
            NAME = "kintai"
            OWNER = "test_browser / テスト"

        with Browsers() as browsers:
            kintai = browsers.launch(Kintai)
            kintai.close()
            assert not closed, "Browsers の持ち物を閉じてしまっている"

        assert closed, "Browsers を抜けたのに閉じていない"

    def test_close_is_safe_to_call_twice(self, monkeypatch):
        """close() を2回呼んでも落ちない。"""
        self._no_real_browser(monkeypatch)

        class Kintai(SiteBase):
            NAME = "kintai"
            OWNER = "test_browser / テスト"

        kintai = Kintai()
        kintai.close()
        kintai.close()


class TestSessionIsNotExposedToCallers:
    """利用側に session を書かせずに済むことを固める。

    session はブラウザの持ち方という内部の都合で、サイトや画面を書く人が
    知らなくてよい。page() / to() があれば書かずに済む。
    """

    @staticmethod
    def _fake_browser(monkeypatch):
        """Edge を起動せずに、起動済みと同じ状態にする。"""

        def enter(self):
            self._driver = MagicMock()
            return self

        monkeypatch.setattr(BrowserSession, "__enter__", enter)
        monkeypatch.setattr(BrowserSession, "__exit__", lambda self, *a: None)

    def test_site_creates_pages_without_session(self, monkeypatch):
        """SiteBase.to() で画面クラスを作れる。"""
        self._fake_browser(monkeypatch)

        class Kintai(SiteBase):
            NAME = "kintai"
            OWNER = "test_browser / テスト"

        with Kintai() as kintai:
            page = kintai.to(Page)

            assert isinstance(page, Page)
            assert page.session is kintai.session

    def test_page_moves_to_the_next_page_without_session(self, monkeypatch):
        """Page.to() で遷移先の画面クラスを作れる。"""
        self._fake_browser(monkeypatch)

        class Kintai(SiteBase):
            NAME = "kintai"
            OWNER = "test_browser / テスト"

        class HomePage(Page):
            pass

        with Kintai() as kintai:
            home = kintai.to(Page).to(HomePage)

            assert isinstance(home, HomePage)
            assert home.session is kintai.session

    def test_page_before_start_is_rejected(self):
        """起動前に page() を呼んだら、最初の操作を待たずに止める。"""

        class Kintai(SiteBase):
            NAME = "kintai"
            OWNER = "test_browser / テスト"

        with pytest.raises(BrowserError):
            Kintai().to(Page)

    def test_downloads_before_start_is_rejected(self):
        """起動前に downloads を触ったら止める。"""

        class Kintai(SiteBase):
            NAME = "kintai"
            OWNER = "test_browser / テスト"

        with pytest.raises(BrowserError):
            _ = Kintai().downloads
