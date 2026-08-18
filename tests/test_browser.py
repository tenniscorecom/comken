"""ブラウザ操作のテスト。

実際の Edge は起動せず、WebDriver をモックに差し替えて配線と安全装置だけを確認する。
ブラウザを起動するテストは実行環境（Edge とドライバーのバージョン）に左右され、
CI でも手元でも安定しないため、ここでは扱わない。
"""

import inspect
import logging
import os
import threading
import time
from unittest.mock import MagicMock

import pytest
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By

from comken.exceptions import (
    BrowsersClosedError,
    BrowsersNotStartedError,
    ConcurrentSessionUseError,
    DriverStartError,
    ElementNotFoundError,
    PopupTabNotOpenedError,
    SessionClosedError,
    SessionNameConflictError,
    SessionNotFoundError,
    SessionNotStartedError,
    SiteConfigError,
    SiteNotStartedError,
)
from comken.toolbox import browser
from comken.toolbox.browser import (
    BackgroundTask,
    BrowserOptions,
    Browsers,
    BrowserSession,
    DownloadDir,
    Locator,
    Page,
    SiteBase,
    SitePage,
)
from comken.toolbox.browser.management.browsers import Browsers as InternalBrowsers
from comken.toolbox.browser.management.sessions import BrowserSession as InternalBrowserSession
from comken.toolbox.browser.management.startup import _build_driver, create_service
from comken.toolbox.browser.management.tasks import BackgroundTask as InternalBackgroundTask
from comken.toolbox.browser.sites import SITES, SampleSite


class TestPublicApi:
    """内部整理後も comken.toolbox.browser の公開入口を維持する。"""

    def test_exports_management_classes_from_browser_package(self):
        """管理クラス3つを従来どおり comken.toolbox.browser からimportできる。"""
        assert BrowserSession is InternalBrowserSession
        assert Browsers is InternalBrowsers
        assert BackgroundTask is InternalBackgroundTask
        assert {"Browsers", "BrowserSession", "BackgroundTask"} <= set(browser.__all__)

    def test_exports_sample_site_without_registering_as_library_site(self):
        """サンプルサイトを公開しつつ、社内システムの一覧には登録しない。"""
        assert SampleSite.NAME
        assert SampleSite.BASE_URL
        assert SampleSite.OWNER
        # 見本を公認サイト扱いして、同じ NAME の利用側サイトを衝突させる回帰を防ぐ。
        assert SampleSite not in SITES


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
        monkeypatch.setattr(
            "comken.toolbox.browser.management.startup.webdriver.Edge", lambda **kwargs: driver
        )

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
            "comken.toolbox.browser.management.startup.webdriver.Edge",
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
        monkeypatch.setattr("comken.toolbox.browser.management.startup.webdriver.Edge", edge)

        session = BrowserSession(
            name="test",
            options=BrowserOptions(),
            download_dir=DownloadDir(path=tmp_path / "dl"),
        )

        with pytest.raises(DriverStartError):
            session.__enter__()

        assert edge.call_count == 1


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


class TestSessionConcurrencyGuard:
    """1セッションを複数スレッドから同時に触らせないことのテスト。"""

    def test_rejects_concurrent_use_from_another_thread(self, tmp_path):
        """他スレッドが操作中のセッションを触ると ConcurrentSessionUseError になる。"""
        session = _make_session(tmp_path)
        holding = threading.Event()
        release = threading.Event()

        def hold_session():
            with session._operating("hold"):
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

        with session._operating("outer"):
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


class TestBrowsersRequiresWith:
    """with を使わない書き方を弾くことのテスト。"""

    def test_rejects_launch_without_with(self, monkeypatch):
        """with に入れずに launch すると、ブラウザを起動する前に止まる。"""
        edge = MagicMock()
        monkeypatch.setattr("comken.toolbox.browser.management.startup.webdriver.Edge", edge)

        browsers = Browsers()

        with pytest.raises(BrowsersNotStartedError):
            browsers.launch_session("kintai")

        edge.assert_not_called()  # 弾かれた時点で何も起きていない

    def test_rejects_start_without_with(self):
        """with に入れずに start しても動かない。"""
        browsers = Browsers()

        with pytest.raises(BrowsersNotStartedError):
            browsers.run_task(lambda: "動いてしまった")

    def test_rejects_getitem_without_with(self):
        """with に入れずにセッションを取り出すこともできない。"""
        browsers = Browsers()

        with pytest.raises(BrowsersNotStartedError):
            browsers["kintai"]

    def test_rejects_launch_after_with(self, monkeypatch):
        """with を抜けた後に使うと BrowsersClosedError になる。"""
        monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
        monkeypatch.setattr(BrowserSession, "__exit__", lambda self, *args: None)

        with Browsers() as browsers:
            browsers.launch_session("kintai")

        with pytest.raises(BrowsersClosedError):
            browsers.launch_session("keiri")

    def test_error_message_shows_correct_form(self):
        """エラーメッセージに、正しい書き方が載っている。"""
        browsers = Browsers()

        with pytest.raises(BrowsersNotStartedError) as exc_info:
            browsers.launch_session("kintai")

        assert "with Browsers() as browsers:" in str(exc_info.value)


class TestBrowsers:
    """複数サイトのまとめ管理のテスト。"""

    def test_rejects_duplicate_name(self, tmp_path, monkeypatch):
        """同じ名前で2回起動すると SessionNameConflictError になる。"""
        monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
        monkeypatch.setattr(BrowserSession, "__exit__", lambda self, *args: None)

        with Browsers() as browsers:
            browsers.launch_session("kintai")
            with pytest.raises(SessionNameConflictError):
                browsers.launch_session("kintai")

    def test_getitem_reports_launched_names(self, tmp_path, monkeypatch):
        """未起動の名前を取り出すと、起動済みの一覧つきで SessionNotFoundError になる。"""
        monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
        monkeypatch.setattr(BrowserSession, "__exit__", lambda self, *args: None)

        with Browsers() as browsers:
            browsers.launch_session("kintai")

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


class TestBrowsersStart:
    """「先に始めておいて、あとで受け取る」形のテスト。"""

    def test_returns_before_task_finishes(self):
        """start は処理の終了を待たずに、すぐ次の行へ進む。"""
        release = threading.Event()

        with Browsers() as browsers:
            task = browsers.run_task(lambda: release.wait(timeout=5) and "done")

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
            task = browsers.run_task(heavy, label="勤怠")
            assert heavy_started.wait(timeout=5)

            light_finished.set()  # 後続の処理（軽い方）がここで終わったとみなす

            assert task.wait(timeout=5) == "重い方"

    def test_wait_reraises_error(self):
        """裏で起きた例外は、wait で受け取ったときに送出される。"""

        def fail():
            raise ValueError("取得に失敗")

        with Browsers() as browsers:
            task = browsers.run_task(fail)

            with pytest.raises(ValueError, match="取得に失敗"):
                task.wait(timeout=5)

    def test_wait_timeout_keeps_task_running(self):
        """待ち時間を過ぎても、処理自体は動き続ける。"""
        release = threading.Event()

        with Browsers() as browsers:
            task = browsers.run_task(lambda: release.wait(timeout=5) and "done", label="勤怠")

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
            browsers.launch_session("kintai")
            browsers.run_task(slow_task)

        assert events == ["処理がおわった", "ブラウザを閉じた"]

    def test_closes_browsers_even_if_waiting_is_interrupted(self, monkeypatch):
        """終了待ちの最中に中断されても、ブラウザは必ず閉じる。

        ここで閉じ損ねると、with を必須にした意味がなくなる
        （Ctrl+C のたびに Edge のプロセスが残る）。
        """
        closed = []
        monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
        monkeypatch.setattr(
            BrowserSession, "__exit__", lambda self, *args: closed.append(self.name)
        )

        with pytest.raises(KeyboardInterrupt), Browsers() as browsers:
            browsers.launch_session("kintai")
            browsers.launch_session("keiri")
            # 終了待ちが中断された状況を作る
            monkeypatch.setattr(
                browsers,
                "_finish_background_tasks",
                MagicMock(side_effect=KeyboardInterrupt()),
            )

        assert closed == ["keiri", "kintai"]

    def test_late_task_can_still_use_sessions(self, monkeypatch):
        """動き出すのが遅れたタスクからでも、ブラウザを取り出せる。

        閉じたことにするタイミングが早すぎると、まだ閉じていないのに
        BrowsersClosedError になる。
        """
        monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
        monkeypatch.setattr(BrowserSession, "__exit__", lambda self, *args: None)
        released = threading.Event()
        taken = []

        def late_task():
            # with を抜ける処理が始まってから動き出す状況を作る
            released.wait(timeout=5)
            taken.append(browsers["kintai"].name)

        with Browsers() as browsers:
            browsers.launch_session("kintai")
            browsers.run_task(late_task, label="遅れて動く処理")
            released.set()

        assert taken == ["kintai"]

    def test_releases_collected_tasks(self):
        """受け取り済みの処理は保持し続けない（繰り返し start しても溜まらない）。"""
        with Browsers() as browsers:
            for _ in range(20):
                browsers.run_task(lambda: "ok").wait(timeout=5)

            assert len(browsers._tasks) <= 1

    def test_label_numbering_keeps_increasing(self):
        """既定の名前は、受け取り済みを手放しても番号が戻らない。"""
        with Browsers() as browsers:
            first = browsers.run_task(lambda: "ok")
            first.wait(timeout=5)
            second = browsers.run_task(lambda: "ok")

            assert (first.label, second.label) == ("処理1", "処理2")

    def test_rejects_parallel_without_with(self):
        """with に入れずに parallel を呼ぶと、引数が空でも弾かれる。"""
        browsers = Browsers()

        with pytest.raises(BrowsersNotStartedError):
            browsers.parallel()

    def test_reports_uncollected_error(self, caplog):
        """wait を呼び忘れた処理の例外も、黙って消えずにログへ出す。"""

        def fail():
            raise ValueError("誰にも受け取られない失敗")

        with caplog.at_level(logging.ERROR), Browsers() as browsers:
            browsers.run_task(fail, label="勤怠")

        assert "勤怠" in caplog.text
        assert "誰にも受け取られない失敗" in caplog.text

    def test_does_not_report_collected_error_twice(self, caplog):
        """wait で受け取り済みの失敗は、終了時に重ねて報告しない。"""

        def fail():
            raise ValueError("受け取り済みの失敗")

        with caplog.at_level(logging.ERROR), Browsers() as browsers:
            task = browsers.run_task(fail, label="勤怠")
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


class TestRemovedNames:
    """作り直しで無くなった名前を使ったときの案内のテスト。"""

    def test_old_driver_name_explains_replacement(self):
        """EdgeDriver を使うと、置き換え先が分かるエラーになる。"""
        import comken.toolbox.browser as browser_package

        with pytest.raises(AttributeError, match="Browsers"):
            _ = browser_package.EdgeDriver

    def test_old_page_name_explains_replacement(self):
        """BasePage を使うと、置き換え先が分かるエラーになる。"""
        import comken.toolbox.browser as browser_package

        with pytest.raises(AttributeError, match="Page"):
            _ = browser_package.BasePage

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

    def test_escape_hatches_are_guarded_too(self, tmp_path):
        """逃げ道（element / js）も同時操作の見張りを通る。

        ここが素通りだと、並列実行時に一番気づきにくい形で壊れる。
        """
        page = self._page(tmp_path)
        holding = threading.Event()
        release = threading.Event()

        def hold_session():
            with page.session._operating("hold"):
                holding.set()
                release.wait(timeout=5)

        holder = threading.Thread(target=hold_session, name="holder")
        holder.start()
        try:
            assert holding.wait(timeout=5)
            with pytest.raises(ConcurrentSessionUseError):
                page.find_element(Locator.id("x"))
            with pytest.raises(ConcurrentSessionUseError):
                page.execute_script("return 1;")
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

        captured: list[BrowserOptions] = []

        real_resolve = InternalBrowsers.launch_session

        def capture(self, name, options=None, download_dir=None):
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
        """NAME が空の SiteBase サブクラスを渡すと SiteConfigError で止まる。"""

        class Unnamed(SiteBase):
            BASE_URL = "https://example.co.jp"
            OPTIONS = BrowserOptions

        monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
        monkeypatch.setattr(BrowserSession, "__exit__", lambda self, *args: None)

        with Browsers() as browsers, pytest.raises(SiteConfigError) as exc_info:
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

        with pytest.raises(BrowsersNotStartedError):
            browsers.launch(Kintai)

        edge.assert_not_called()  # 弾かれた時点で何も起きていない

    def test_rejects_duplicate_site_name(self, tmp_path, monkeypatch):
        """同じ NAME の SiteBase を2回起動すると SessionNameConflictError になる。"""
        monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
        monkeypatch.setattr(BrowserSession, "__exit__", lambda self, *args: None)

        class Kintai(SiteBase):
            NAME = "kintai"
            OPTIONS = BrowserOptions
            OWNER = "test_browser / テスト"

        with Browsers() as browsers:
            browsers.launch(Kintai)
            with pytest.raises(SessionNameConflictError):
                browsers.launch(Kintai)


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

        with pytest.raises(BrowsersNotStartedError):
            browsers.launch_session("kintai")

        edge.assert_not_called()


class TestSiteStandsAlone:
    """SiteBase を単体で使える（Browsers を経由しない）ことを固める。

    1サイトだけ触るツールで `with Browsers() as browsers:` を挟ませたくない。
    Salesforce の `with Sandbox() as sf:` と同じ形で始められるようにする。
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

        with pytest.raises(SiteNotStartedError):
            Kintai().to(Page)

    def test_downloads_before_start_is_rejected(self):
        """起動前に downloads を触ったら止める。"""

        class Kintai(SiteBase):
            NAME = "kintai"
            OWNER = "test_browser / テスト"

        with pytest.raises(SiteNotStartedError):
            _ = Kintai().downloads
