"""ブラウザ操作のテスト。

実際の Edge は起動せず、WebDriver をモックに差し替えて配線と安全装置だけを確認する。
ブラウザを起動するテストは実行環境（Edge とドライバーのバージョン）に左右され、
CI でも手元でも安定しないため、ここでは扱わない。
"""

import logging
import shutil
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By

from comken.browser import BrowserOptions, Browsers, DownloadDir, Locator, Page, SitePage
from comken.browser.driver_update import _major, _pick_source, _replace_driver
from comken.browser.session import BrowserSession
from comken.exceptions import (
    ConcurrentSessionUseError,
    DriverStartError,
    ElementNotFoundError,
    PopupTabNotOpenedError,
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


class TestSessionStartFailure:
    """起動に失敗したときに、プロセスもフォルダも残さないことのテスト。"""

    def test_quits_driver_when_initialization_fails(self, tmp_path, monkeypatch):
        """起動後の初期化で失敗したら、掴んだブラウザを必ず閉じる。

        ここで閉じ損ねると、誰も参照していない Edge プロセスが残り続ける。
        """
        driver = MagicMock()
        driver.implicitly_wait.side_effect = RuntimeError("初期化に失敗")
        monkeypatch.setattr("comken.browser.session.webdriver.Edge", lambda **kwargs: driver)

        session = BrowserSession(
            name="test",
            options=BrowserOptions(),
            download_dir=DownloadDir(path=tmp_path / "dl"),
        )

        with pytest.raises(DriverStartError):
            session.__enter__()

        driver.quit.assert_called_once_with()

    def test_cleans_download_dir_exactly_once_on_failure(self, tmp_path, monkeypatch):
        """起動に失敗したとき、ダウンロードフォルダの後始末はちょうど1回だけ行う。

        __enter__ が失敗すると with の __exit__ は呼ばれないため、
        後始末は起動処理の側で完結している必要がある。
        """
        monkeypatch.setattr(
            "comken.browser.session.webdriver.Edge",
            MagicMock(side_effect=RuntimeError("起動に失敗")),
        )
        download_dir = MagicMock(wraps=DownloadDir(path=tmp_path / "dl"))
        download_dir.path = tmp_path / "dl"

        session = BrowserSession(name="test", options=BrowserOptions(), download_dir=download_dir)

        with pytest.raises(DriverStartError):
            session.__enter__()

        download_dir.__exit__.assert_called_once()

    def test_does_not_retry_when_no_source_dir(self, tmp_path, monkeypatch):
        """配布フォルダが未設定なら、ドライバー更新も再試行もしない。"""
        edge = MagicMock(side_effect=RuntimeError("起動に失敗"))
        monkeypatch.setattr("comken.browser.session.webdriver.Edge", edge)

        session = BrowserSession(
            name="test",
            options=BrowserOptions(),
            download_dir=DownloadDir(path=tmp_path / "dl"),
        )

        with pytest.raises(DriverStartError):
            session.__enter__()

        assert edge.call_count == 1


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
        """新しいタブが開かなければ PopupTabNotOpenedError になる。"""
        session = _make_session(tmp_path)
        driver = session._driver
        driver.current_window_handle = "main"
        driver.window_handles = ["main"]

        with pytest.raises(PopupTabNotOpenedError), session.popup_tab(timeout=1):
            pass


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

        with pytest.raises(RuntimeError), Browsers() as browsers:
            browsers.launch("kintai")
            browsers.launch("keiri")
            raise RuntimeError("処理中のエラー")

        # ExitStack は起動と逆順に閉じる
        assert closed == ["keiri", "kintai"]


class TestBrowsersStart:
    """「先に始めておいて、あとで受け取る」形のテスト。"""

    def test_returns_before_task_finishes(self):
        """start は処理の終了を待たずに、すぐ次の行へ進む。"""
        release = threading.Event()

        with Browsers() as browsers:
            task = browsers.start(lambda: release.wait(timeout=5) and "done")

            # 処理はまだ終わっていないのに、ここまで進んでいる
            assert not task.is_done
            release.set()
            assert task.wait(timeout=5) == "done"
            assert task.is_done

    def test_other_work_progresses_while_waiting(self):
        """重い処理を待っている間に、後続の行が進む。"""
        heavy_started = threading.Event()
        light_finished = threading.Event()

        def heavy():
            heavy_started.set()
            # 後続の処理が先に終わるまで待つ。順番に動いていればここで詰まる
            assert light_finished.wait(timeout=5)
            return "重い方"

        with Browsers() as browsers:
            task = browsers.start(heavy, label="勤怠")
            assert heavy_started.wait(timeout=5)

            light_finished.set()  # 後続の処理（軽い方）がここで終わったとみなす

            assert task.wait(timeout=5) == "重い方"

    def test_wait_reraises_error(self):
        """裏で起きた例外は、wait で受け取ったときに送出される。"""
        def fail():
            raise ValueError("取得に失敗")

        with Browsers() as browsers:
            task = browsers.start(fail)

            with pytest.raises(ValueError, match="取得に失敗"):
                task.wait(timeout=5)

    def test_wait_timeout_keeps_task_running(self):
        """待ち時間を過ぎても、処理自体は動き続ける。"""
        release = threading.Event()

        with Browsers() as browsers:
            task = browsers.start(lambda: release.wait(timeout=5) and "done", label="勤怠")

            with pytest.raises(TimeoutError, match="勤怠"):
                task.wait(timeout=0.1)

            release.set()
            assert task.wait(timeout=5) == "done"

    def test_waits_for_tasks_before_closing_browsers(self, tmp_path, monkeypatch):
        """with を抜けるとき、裏の処理が終わってからブラウザを閉じる。

        先に閉じると、操作の途中でブラウザが消えて原因の分かりにくいエラーになる。
        """
        events = []
        monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
        monkeypatch.setattr(
            BrowserSession, "__exit__", lambda self, *args: events.append("ブラウザを閉じた")
        )

        def slow_task():
            time.sleep(0.1)
            events.append("処理がおわった")

        with Browsers() as browsers:
            browsers.launch("kintai")
            browsers.start(slow_task)

        assert events == ["処理がおわった", "ブラウザを閉じた"]

    def test_reports_uncollected_error(self, caplog):
        """wait を呼び忘れた処理の例外も、黙って消えずにログへ出す。"""
        def fail():
            raise ValueError("誰にも受け取られない失敗")

        with caplog.at_level(logging.ERROR), Browsers() as browsers:
            browsers.start(fail, label="勤怠")

        assert "勤怠" in caplog.text
        assert "誰にも受け取られない失敗" in caplog.text

    def test_does_not_report_collected_error_twice(self, caplog):
        """wait で受け取り済みの失敗は、終了時に重ねて報告しない。"""
        def fail():
            raise ValueError("受け取り済みの失敗")

        with caplog.at_level(logging.ERROR), Browsers() as browsers:
            task = browsers.start(fail, label="勤怠")
            with pytest.raises(ValueError):
                task.wait(timeout=5)

        assert "受け取られないまま終了" not in caplog.text


class TestBrowsersParallel:
    """まとめて同時実行するときのテスト。"""

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

        with Browsers() as browsers, pytest.raises(ValueError, match="取得に失敗"):
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

        with Browsers() as browsers, pytest.raises(ValueError):
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

    def test_ignores_version_in_source_dir_own_path(self, tmp_path, caplog):
        """配布フォルダ自身のパスに含まれる数字では、一致と判定しない。

        \\\\サーバー\\ツール131\\ のような親フォルダがあると、配下のどのドライバーも
        メジャー131に一致したことになり、不一致に気づけないまま使われてしまう。
        """
        source_dir = tmp_path / "ツール131"
        folder = source_dir / "130.0.2849.68"
        folder.mkdir(parents=True)
        (folder / "msedgedriver.exe").write_bytes(b"x")

        with caplog.at_level(logging.WARNING):
            picked = _pick_source(source_dir, "131.0.2903.86")

        # 選ぶファイルは1つしかないが、「一致した」ではなく
        # 「一致が無いので最新で代用した」と扱われる必要がある
        assert picked.parent.name == "130.0.2849.68"
        assert "見つからない" in caplog.text

    def test_raises_when_no_driver_found(self, tmp_path):
        """配布フォルダに1つも無ければ FileNotFoundError になる。"""
        with pytest.raises(FileNotFoundError):
            _pick_source(tmp_path, "131.0.2903.86")

    def test_replaces_via_temporary_file(self, tmp_path, monkeypatch):
        """更新は一時ファイル経由で行い、途中の壊れた exe を残さない。

        共有フォルダから直接上書きすると、失敗したときに中途半端なファイルが
        残り、別のプロセスがそれを掴んでしまう。
        """
        source = tmp_path / "source" / "msedgedriver.exe"
        source.parent.mkdir()
        source.write_bytes(b"new-driver")
        target = tmp_path / "bin" / "msedgedriver.exe"
        target.parent.mkdir()
        target.write_bytes(b"old-driver")

        copied = []
        real_copy = shutil.copy2

        def record_copy(src, dst):
            copied.append(Path(dst).name)
            return real_copy(src, dst)

        monkeypatch.setattr("comken.browser.driver_update.shutil.copy2", record_copy)

        _replace_driver(source, target)

        assert target.read_bytes() == b"new-driver"
        assert copied and copied[0] != target.name  # いったん別名へ書いている
        assert list(target.parent.iterdir()) == [target]  # 一時ファイルが残らない

    def test_reports_locked_driver_with_guidance(self, tmp_path, monkeypatch):
        """掴まれていて置き換えられない場合は、対処を添えて知らせる。"""
        source = tmp_path / "msedgedriver.exe"
        source.write_bytes(b"new-driver")
        target = tmp_path / "bin" / "msedgedriver.exe"

        monkeypatch.setattr(
            "comken.browser.driver_update.shutil.copy2",
            MagicMock(side_effect=PermissionError("使用中")),
        )

        with pytest.raises(PermissionError, match="実行中の自動化"):
            _replace_driver(source, target)


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

    def test_elements_returns_all_matches(self, tmp_path):
        """elements は一致した全要素をリストで返す。"""
        page = self._page(tmp_path)
        rows = [MagicMock(), MagicMock(), MagicMock()]
        page._wait.until.return_value = rows

        assert page.elements(Locator.css("table tr")) == rows

    def test_elements_reports_selector_when_none_found(self, tmp_path):
        """1件も見つからなければ、セレクター付きのエラーになる。"""
        page = self._page(tmp_path)
        page._wait.until.side_effect = TimeoutException()

        with pytest.raises(ElementNotFoundError) as exc_info:
            page.elements(Locator.css("table tr"))

        assert "table tr" in str(exc_info.value)

    def test_escape_hatches_are_guarded_too(self, tmp_path):
        """逃げ道（element / js）も同時操作の見張りを通る。

        ここが素通りだと、並列実行時に一番気づきにくい形で壊れる。
        """
        page = self._page(tmp_path)
        holding = threading.Event()
        release = threading.Event()

        def hold_session():
            with page.session.operating("hold"):
                holding.set()
                release.wait(timeout=5)

        holder = threading.Thread(target=hold_session, name="holder")
        holder.start()
        try:
            assert holding.wait(timeout=5)
            with pytest.raises(ConcurrentSessionUseError):
                page.element(Locator.id("x"))
            with pytest.raises(ConcurrentSessionUseError):
                page.js("return 1;")
        finally:
            release.set()
            holder.join(timeout=5)

    def test_frame_returns_to_default_content_on_error(self, tmp_path):
        """iframe の中で例外が出ても、元の画面へ戻る。"""
        page = self._page(tmp_path)

        with pytest.raises(RuntimeError), page.frame(Locator.id("content")):
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
