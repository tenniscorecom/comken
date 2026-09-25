"""comken.run の動作を確認する。

`comken.run.backoffice` / `comken.run.intranet` は、社内 RPA 基盤のローカル実装。
開始メッセージを出し、`main()` を呼んでその戻り値をそのまま返し、終了メッセージと
実行時間（HH:MM）を出す（メッセージと実行時間は下の ``TestRunMessages`` で検証する）。
"""

from __future__ import annotations

import datetime as _dt
import logging
from unittest import mock

import pytest

from comken import run as run_module
from comken.core.calendar._calendar import _Calendar, _set_calendar_for_test
from comken.core.clock import today
from comken.run import backoffice, intranet


class TestBackoffice:
    """`backoffice` のテスト。"""

    def test_calls_main_and_returns_its_result(self) -> None:
        """`main()` を呼んで、その戻り値をそのまま返す。"""
        sentinel_main = mock.Mock(return_value="ok")
        result = backoffice(sentinel_main, "project")
        sentinel_main.assert_called_once_with()
        assert result == "ok"

    def test_main_is_actually_invoked(self) -> None:
        """`main` が呼ばれないと結果が決まらない（Mock の呼び出し回数で担保）。"""
        not_called_main = mock.Mock()
        backoffice(not_called_main, "project")
        assert not_called_main.call_count == 1

    def test_exception_in_main_propagates_unchanged(self) -> None:
        """`main` 内で出た例外は変換されず、そのまま呼び出し側へ伝わる。"""
        boom_main = mock.Mock(side_effect=RuntimeError("boom"))
        with pytest.raises(RuntimeError, match="boom"):
            backoffice(boom_main, "project")


class TestIntranet:
    """`intranet` のテスト。"""

    def test_calls_main_and_returns_its_result(self) -> None:
        """`main()` を呼んで、その戻り値をそのまま返す。"""
        sentinel_main = mock.Mock(return_value="ok")
        result = intranet(sentinel_main, "project")
        sentinel_main.assert_called_once_with()
        assert result == "ok"

    def test_main_is_actually_invoked(self) -> None:
        """`main` が呼ばれないと結果が決まらない（Mock の呼び出し回数で担保）。"""
        not_called_main = mock.Mock()
        intranet(not_called_main, "project")
        assert not_called_main.call_count == 1

    def test_exception_in_main_propagates_unchanged(self) -> None:
        """`main` 内で出た例外は変換されず、そのまま呼び出し側へ伝わる。"""
        boom_main = mock.Mock(side_effect=RuntimeError("boom"))
        with pytest.raises(RuntimeError, match="boom"):
            intranet(boom_main, "project")


@pytest.mark.parametrize(
    "project_name",
    ["", "ascii-name", "日本語のプロジェクト名"],
)
def test_project_name_is_accepted_for_backoffice(project_name: str) -> None:
    """`project_name` が何の値でもエラーにならない（型を問わない）。"""
    sentinel_main = mock.Mock(return_value=None)
    assert backoffice(sentinel_main, project_name) is None


@pytest.mark.parametrize(
    "project_name",
    ["", "ascii-name", "日本語のプロジェクト名"],
)
def test_project_name_is_accepted_for_intranet(project_name: str) -> None:
    """`intranet` も `project_name` が何の値でもエラーにならない。"""
    sentinel_main = mock.Mock(return_value=None)
    assert intranet(sentinel_main, project_name) is None


# ── 起動時の祝日カレンダー期限切れ警告 ─────────────────────────────────────


def _near_expiry_calendar(days_until_last: int) -> _Calendar:
    """``days_until_last`` 日後に最終収録日を持つ小さなカレンダーを作る。"""
    last = today() + _dt.timedelta(days=days_until_last)
    return _Calendar({last: "テスト用の最終祝日"})


class TestStartupCalendarExpiryWarning:
    """``backoffice`` / ``intranet`` の起動直後に、祝日カレンダーの期限切れ警告を出す。

    ``_singleton``（モジュールグローバル）はテスト間でリークしないよう
    ``setup_method`` / ``teardown_method`` で必ず ``None`` にリセットする。
    """

    def setup_method(self) -> None:
        _set_calendar_for_test(None)

    def teardown_method(self) -> None:
        _set_calendar_for_test(None)

    def test_backoffice_warns_before_main_when_near_expiry(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """``backoffice`` は期限切れが近いとき ``main`` より前に WARNING ログを出す。

        ``main`` が呼ばれた瞬間に WARNING が出ていたか (``caplog.records``
        の状態) を直接確認するのではなく、``main`` の中で ``caplog.records``
        を読み取って「``main`` の時点では既に WARNING が記録されている」
        ことを確認する。これで「WARNING が ``main`` より前に評価された」
        ことを担保する。
        """
        _set_calendar_for_test(_near_expiry_calendar(days_until_last=15))

        expiry_warnings_seen_in_main: list[int] = []

        def record_main() -> str:
            expiry_warnings_seen_in_main.append(
                sum(
                    1
                    for r in caplog.records
                    if r.levelno == logging.WARNING and "収録期限" in r.getMessage()
                )
            )
            return "ok"

        with caplog.at_level(logging.WARNING, logger="comken.core.calendar._calendar"):
            result = backoffice(record_main, "project")

        assert result == "ok"
        # ``main`` が実行された時点では既に期限切れ WARNING が 1件出ている
        assert expiry_warnings_seen_in_main == [1]
        # ``backoffice`` 完了後の最終形でも 1件のまま（重複発火していない）
        final_count = sum(
            1
            for r in caplog.records
            if r.levelno == logging.WARNING and "収録期限" in r.getMessage()
        )
        assert final_count == 1

    def test_intranet_warns_before_main_when_near_expiry(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """``intranet`` も同様に ``main`` より前に WARNING ログを出す。"""
        _set_calendar_for_test(_near_expiry_calendar(days_until_last=15))

        expiry_warnings_seen_in_main: list[int] = []

        def record_main() -> None:
            expiry_warnings_seen_in_main.append(
                sum(
                    1
                    for r in caplog.records
                    if r.levelno == logging.WARNING and "収録期限" in r.getMessage()
                )
            )

        with caplog.at_level(logging.WARNING, logger="comken.core.calendar._calendar"):
            intranet(record_main, "project")

        assert expiry_warnings_seen_in_main == [1]
        final_count = sum(
            1
            for r in caplog.records
            if r.levelno == logging.WARNING and "収録期限" in r.getMessage()
        )
        assert final_count == 1

    def test_backoffice_does_not_warn_when_far_from_expiry(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """``EXPIRING_WARNING_DAYS`` 以上先なら警告は出ない（``main`` は普通に動く）。"""
        _set_calendar_for_test(_near_expiry_calendar(days_until_last=120))

        with caplog.at_level(logging.WARNING, logger="comken.core.calendar._calendar"):
            assert backoffice(lambda: "ok", "project") == "ok"

        expiry_warnings = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and "収録期限" in r.getMessage()
        ]
        assert expiry_warnings == []

    def test_intranet_does_not_warn_when_far_from_expiry(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """``intranet`` も遠い期限なら警告を出さない。"""
        _set_calendar_for_test(_near_expiry_calendar(days_until_last=120))

        with caplog.at_level(logging.WARNING, logger="comken.core.calendar._calendar"):
            assert intranet(lambda: "ok", "project") == "ok"

        expiry_warnings = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and "収録期限" in r.getMessage()
        ]
        assert expiry_warnings == []


# ── 開始・終了メッセージと実行時間（HH:MM） ────────────────────────────────


@pytest.fixture
def fake_clock(monkeypatch: pytest.MonkeyPatch):
    """``main()`` の実行にかかった秒数を、テストで決められるようにする。"""
    clock = {"now": 1000.0}
    monkeypatch.setattr(run_module.time, "perf_counter", lambda: clock["now"])
    return clock


class TestFormatHhmm:
    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [
            (0, "00:00"),
            (59, "00:00"),  # 分未満は切り捨て
            (60, "00:01"),
            (3661, "01:01"),
            (86400 + 90, "24:01"),
            (100 * 3600, "100:00"),  # 100 時間を超えても崩れない
        ],
    )
    def test_formats_hours_and_minutes(self, seconds: float, expected: str) -> None:
        assert run_module._format_hhmm(seconds) == expected


class TestRunMessages:
    def test_returns_the_result_of_main(self, fake_clock) -> None:
        assert backoffice(lambda: 42, "テスト") == 42

    def test_logs_start_and_finish_with_elapsed_time(self, fake_clock, caplog) -> None:
        def main() -> None:
            fake_clock["now"] += 3661  # 1時間1分1秒

        with caplog.at_level(logging.INFO, logger="comken.run"):
            backoffice(main, "売上集計")

        messages = [record.getMessage() for record in caplog.records]
        assert messages == [
            "【バックオフィス】売上集計 を開始します",
            "【バックオフィス】売上集計 が終了しました（実行時間 01:01）",
        ]

    def test_intranet_uses_its_own_label(self, fake_clock, caplog) -> None:
        with caplog.at_level(logging.INFO, logger="comken.run"):
            intranet(lambda: None, "勤怠")

        assert all("【イントラネット】" in record.getMessage() for record in caplog.records)

    def test_failure_is_logged_with_elapsed_time_and_reraised(self, fake_clock, caplog) -> None:
        def main() -> None:
            fake_clock["now"] += 125
            raise RuntimeError("失敗")

        with caplog.at_level(logging.INFO, logger="comken.run"), pytest.raises(RuntimeError):
            backoffice(main, "売上集計")

        failure = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert [r.getMessage() for r in failure] == [
            "【バックオフィス】売上集計 が異常終了しました（実行時間 00:02）"
        ]
