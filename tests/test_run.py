"""comken.run の動作を確認する。

`comken.run.backoffice` / `comken.run.intranet` は、社内 RPA 基盤の最小実装。
`main()` を呼んでその戻り値をそのまま返すだけ。``project_name`` は
呼び出し規約（シグネチャ）を保つために受け取るが、現状では未使用。
"""

from __future__ import annotations

import datetime as _dt
import logging
from unittest import mock

import pytest

from comken.core.clock import today
from comken.core.holidays import Holiday, HolidayCalendar, set_default_calendar
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


def _near_expiry_calendar(days_until_last: int) -> HolidayCalendar:
    """``days_until_last`` 日後に最終収録日を持つ小さなカレンダーを作る。"""
    last = today() + _dt.timedelta(days=days_until_last)
    return HolidayCalendar([Holiday(date=last, name="テスト用の最終祝日")])


class TestStartupCalendarExpiryWarning:
    """``backoffice`` / ``intranet`` の起動直後に、祝日カレンダーの期限切れ警告を出す。

    ``_default_calendar`` はモジュールグローバルなので、テスト間で
    リークしないよう ``setup_method`` / ``teardown_method`` で必ず ``None``
    にリセットする (``TestDefaultCalendar`` と同じ流儀)。
    """

    def setup_method(self) -> None:
        set_default_calendar(None)

    def teardown_method(self) -> None:
        set_default_calendar(None)

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
        set_default_calendar(_near_expiry_calendar(days_until_last=15))

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

        with caplog.at_level(logging.WARNING, logger="comken.core.holidays.calendar"):
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
        set_default_calendar(_near_expiry_calendar(days_until_last=15))

        expiry_warnings_seen_in_main: list[int] = []

        def record_main() -> None:
            expiry_warnings_seen_in_main.append(
                sum(
                    1
                    for r in caplog.records
                    if r.levelno == logging.WARNING and "収録期限" in r.getMessage()
                )
            )

        with caplog.at_level(logging.WARNING, logger="comken.core.holidays.calendar"):
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
        set_default_calendar(_near_expiry_calendar(days_until_last=120))

        with caplog.at_level(logging.WARNING, logger="comken.core.holidays.calendar"):
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
        set_default_calendar(_near_expiry_calendar(days_until_last=120))

        with caplog.at_level(logging.WARNING, logger="comken.core.holidays.calendar"):
            assert intranet(lambda: "ok", "project") == "ok"

        expiry_warnings = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and "収録期限" in r.getMessage()
        ]
        assert expiry_warnings == []
