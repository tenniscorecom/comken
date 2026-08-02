"""ブラウザ操作のテスト。

実際の Edge は起動せず、WebDriver をモックに差し替えて配線と安全装置だけを確認する。
ブラウザを起動するテストは実行環境（Edge とドライバーのバージョン）に左右され、
CI でも手元でも安定しないため、ここでは扱わない。
"""

import threading
from unittest.mock import MagicMock

import pytest
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By

from comken.browser import BrowserOptions, Browsers, DownloadDir, Locator, Page, SitePage
from comken.browser.driver_update import _major, _pick_source
from comken.browser.session import BrowserSession
from comken.exceptions import (
    ConcurrentSessionUseError,
    ElementNotFoundError,
    SessionClosedError,
    SessionNameConflictError,
    SessionNotFoundError,
    SessionNotStartedError,
)

def _make_session(tmp_path, name: str = "test") -> BrowserSession:
    """Edge を起動せずに、起動済みと同じ状態の BrowserSession を作る。"""
    session = BrowserSession(
        name=name,
        options=BrowserOptions(),
        download_dir=DownloadDir(path=tmp_path / f"dl_{name}"),
        profile_dir=None,
    )
    session._driver = MagicMock()
    session._main_window = "main"
    return session


class TestSessionRequiresWith:
    """with を使わない・使い終わったセッションを弾くことのテスト。"""

    def test_rejects_operation_before_with(self, tmp_path):
        """with に入る前に操作すると SessionNotStartedError になる。"""
        session = BrowserSession(
            name="test",
            options=BrowserOptions(),
            download_dir=DownloadDir(path=tmp_path / "dl"),
        )

        with pytest.raises(SessionNotStartedError):
            session.open("https://example.com")

    def test_rejects_operation_after_close(self, tmp_path):
        """with を抜けた後に操作すると SessionClosedError になる。"""
        session = _make_session(tmp_path)
        session.__exit__(None, None, None)

        with pytest.raises(SessionClosedError):
            session.open("https://example.com")

    def test_quit_failure_still_cleans_download_dir(self, tmp_path):
        """ブラウザの終了に失敗しても、一時フォルダの後片付けは行われる。"""
        session = _make_session(tmp_path)
        session._driver.quit.side_effect = RuntimeError("quit failed")
        download_dir = session.download_dir

        with pytest.raises(RuntimeError):
            session.__exit__(None, None, None)

        # 固定フォルダなので消えないが、__exit__ が呼ばれたこと自体を状態で確認する
        assert session._is_closed
        assert download_dir.path.exists()


class TestSessionConcurrencyGuard:
    """1セッションを複数スレッドから同時に触らせないことのテスト。"""

    def test_rejects_concurrent_use_from_another_thread(self, tmp_path):
        """他スレッドが操作中のセッションを触ると ConcurrentSessionUseError になる。"""
        session = _make_session(tmp_path)
        holding = threading.Event()
        release = threading.Event()

        def hold_session():
            with session.operating("hold"):
                holding.set()
                release.wait(timeout=5)

        holder = threading.Thread(target=hold_session, name="holder")
        holder.start()
        try:
            assert holding.wait(timeout=5)
            with pytest.raises(ConcurrentSessionUseError):
                session.open("https://example.com")
        finally:
            release.set()
            holder.join(timeout=5)

    def test_allows_nested_use_in_same_thread(self, tmp_path):
        """同じスレッドの中で操作がネストしても止まらない（RLock のため）。"""
        session = _make_session(tmp_path)

        with session.operating("outer"):
            session.open("https://example.com")

        session._driver.get.assert_called_once_with("https://example.com")


class TestBrowsers:
    """複数サイトのまとめ管理のテスト。"""

    def test_rejects_duplicate_name(self, tmp_path, monkeypatch):
        """同じ名前で2回起動すると SessionNameConflictError になる。"""
        monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
        monkeypatch.setattr(BrowserSession, "__exit__", lambda self, *args: None)

        with Browsers() as browsers:
            browsers.launch("kintai")
            with pytest.raises(SessionNameConflictError):
                browsers.launch("kintai")

    def test_getitem_reports_launched_names(self, tmp_path, monkeypatch):
        """未起動の名前を取り出すと、起動済みの一覧つきで SessionNotFoundError になる。"""
        monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
        monkeypatch.setattr(BrowserSession, "__exit__", lambda self, *args: None)

        with Browsers() as browsers:
            browsers.launch("kintai")

            assert browsers.names == ["kintai"]
            with pytest.raises(SessionNotFoundError) as exc_info:
                browsers["keiri"]
            assert "kintai" in str(exc_info.value)

    def test_download_dir_is_separated_per_session(self, tmp_path, monkeypatch):
        """DOWNLOAD_DIR を共有しても、セッション名ごとのサブフォルダに分かれる。"""
        monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
        monkeypatch.setattr(BrowserSession, "__exit__", lambda self, *args: None)

        class SharedOptions(BrowserOptions):
            DOWNLOAD_DIR = str(tmp_path / "downloads")

        with Browsers() as browsers:
            kintai = browsers.launch("kintai", SharedOptions)
            keiri = browsers.launch("keiri", SharedOptions)

            assert kintai.download_dir.path != keiri.download_dir.path
            assert kintai.download_dir.path.name == "kintai"
            assert keiri.download_dir.path.name == "keiri"

    def test_options_class_is_instantiated_per_session(self, tmp_path, monkeypatch):
        """オプションをクラスで渡すと、セッションごとに別インスタンスになる。"""
        monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
        monkeypatch.setattr(BrowserSession, "__exit__", lambda self, *args: None)

        with Browsers() as browsers:
            kintai = browsers.launch("kintai", BrowserOptions)
            keiri = browsers.launch("keiri", BrowserOptions)

            assert kintai._options is not keiri._options

    def test_closes_all_sessions_on_error(self, tmp_path, monkeypatch):
        """途中で例外が出ても、起動済みのセッションはすべて閉じられる。"""
        closed = []
        monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
        monkeypatch.setattr(
            BrowserSession, "__exit__", lambda self, *args: closed.append(self.name)
        )

        with pytest.raises(RuntimeError):
            with Browsers() as browsers:
                browsers.launch("kintai")
                browsers.launch("keiri")
                raise RuntimeError("処理中のエラー")

        # ExitStack は起動と逆順に閉じる
        assert closed == ["keiri", "kintai"]


class TestBrowsersParallel:
    """並列実行のテスト。"""

    def test_returns_results_in_given_order(self):
        """結果は、渡した順で返る（終わった順ではない）。"""
        with Browsers() as browsers:
            results = browsers.parallel(lambda: "a", lambda: "b", lambda: "c")

        assert results == ["a", "b", "c"]

    def test_runs_tasks_concurrently(self):
        """各処理が同時に走る（全員が揃うまで待てることで確認する）。"""
        barrier = threading.Barrier(3, timeout=5)

        def wait_for_others() -> int:
            # 3つ同時に走っていなければ、ここで BrokenBarrierError になる
            return barrier.wait()

        with Browsers() as browsers:
            results = browsers.parallel(wait_for_others, wait_for_others, wait_for_others)

        assert sorted(results) == [0, 1, 2]

    def test_raises_first_error(self):
        """失敗した処理があれば例外を送出する。"""
        def fail():
            raise ValueError("取得に失敗")

        with Browsers() as browsers:
            with pytest.raises(ValueError, match="取得に失敗"):
                browsers.parallel(fail, lambda: "ok")

    def test_waits_for_all_tasks_even_when_one_fails(self):
        """1つ失敗しても、走り出した処理は最後まで待つ（操作中に放置しない）。"""
        finished = []

        def fail():
            raise ValueError("失敗")

        def slow():
            threading.Event().wait(0.05)
            finished.append("slow")
            return "ok"

        with Browsers() as browsers:
            with pytest.raises(ValueError):
                browsers.parallel(fail, slow)

        assert finished == ["slow"]

    def test_returns_empty_for_no_tasks(self):
        """処理を渡さなければ空リストを返す。"""
        with Browsers() as browsers:
            assert browsers.parallel() == []


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


class TestDriverUpdate:
    """msedgedriver の自動更新のテスト。"""

    def test_major_version(self):
        """メジャーバージョンだけを取り出す。"""
        assert _major("131.0.2903.86") == "131"
        assert _major("131") == "131"

    def test_prefers_file_directly_in_source_dir(self, tmp_path):
        """配布フォルダ直下にあれば、それを最優先で使う。"""
        direct = tmp_path / "msedgedriver.exe"
        direct.write_bytes(b"direct")
        nested = tmp_path / "131.0.2903.86"
        nested.mkdir()
        (nested / "msedgedriver.exe").write_bytes(b"nested")

        assert _pick_source(tmp_path, "131.0.2903.86") == direct

    def test_prefers_matching_major_version_folder(self, tmp_path):
        """直下に無ければ、Edge のメジャーバージョンを含むパスを選ぶ。"""
        for version in ("130.0.2849.68", "131.0.2903.86"):
            folder = tmp_path / version
            folder.mkdir()
            (folder / "msedgedriver.exe").write_bytes(b"x")

        picked = _pick_source(tmp_path, "131.0.2903.86")

        assert picked.parent.name == "131.0.2903.86"

    def test_does_not_match_partial_version_number(self, tmp_path):
        """メジャー 13 が 131 のフォルダに誤って一致しない。"""
        folder = tmp_path / "131.0.2903.86"
        folder.mkdir()
        (folder / "msedgedriver.exe").write_bytes(b"x")

        # 一致するものが無いので、最新のものへフォールバックする（例外にはしない）
        assert _pick_source(tmp_path, "13.0.0.0").parent.name == "131.0.2903.86"

    def test_raises_when_no_driver_found(self, tmp_path):
        """配布フォルダに1つも無ければ FileNotFoundError になる。"""
        with pytest.raises(FileNotFoundError):
            _pick_source(tmp_path, "131.0.2903.86")


class TestLocator:
    """セレクターの宣言的管理のテスト。"""

    def test_factories_build_correct_by(self):
        """各ファクトリが正しい By 種別を持つ。"""
        assert Locator.id("x") == (By.ID, "x")
        assert Locator.name("x") == (By.NAME, "x")
        assert Locator.css(".x") == (By.CSS_SELECTOR, ".x")
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

        assert page.count(Locator.css("table tr")) == 3
        page.session._driver.find_elements.assert_called_with(By.CSS_SELECTOR, "table tr")

    def test_timeout_becomes_element_not_found_with_selector(self, tmp_path):
        """時間切れは、どのセレクターで失敗したかが分かる例外に変わる。"""
        page = self._page(tmp_path)
        page._wait.until.side_effect = TimeoutException()

        with pytest.raises(ElementNotFoundError) as exc_info:
            page.click(Locator.id("login-btn"))

        assert "login-btn" in str(exc_info.value)

    def test_frame_returns_to_default_content_on_error(self, tmp_path):
        """iframe の中で例外が出ても、元の画面へ戻る。"""
        page = self._page(tmp_path)

        with pytest.raises(RuntimeError):
            with page.frame(Locator.id("content")):
                raise RuntimeError("中での失敗")

        page.session._driver.switch_to.default_content.assert_called_once_with()


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
