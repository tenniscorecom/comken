"""comken.run（backoffice / intranet）のテスト。

開始メッセージ → main() → 終了メッセージと実行時間（HH:MM）の流れを確かめる。
"""

import logging

import pytest

from comken import run


@pytest.fixture
def fake_clock(monkeypatch: pytest.MonkeyPatch):
    """``main()`` の実行にかかった秒数を、テストで決められるようにする。"""
    clock = {"now": 1000.0}
    monkeypatch.setattr(run.time, "perf_counter", lambda: clock["now"])
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
        assert run._format_hhmm(seconds) == expected


class TestRunFlow:
    def test_returns_the_result_of_main(self, fake_clock) -> None:
        assert run.backoffice(lambda: 42, "テスト") == 42

    def test_logs_start_and_finish_with_elapsed_time(self, fake_clock, caplog) -> None:
        def main() -> None:
            fake_clock["now"] += 3661  # 1時間1分1秒

        with caplog.at_level(logging.INFO, logger="comken.run"):
            run.backoffice(main, "売上集計")

        messages = [record.getMessage() for record in caplog.records]
        assert messages == [
            "【バックオフィス】売上集計 を開始します",
            "【バックオフィス】売上集計 が終了しました（実行時間 01:01）",
        ]

    def test_intranet_uses_its_own_label(self, fake_clock, caplog) -> None:
        with caplog.at_level(logging.INFO, logger="comken.run"):
            run.intranet(lambda: None, "勤怠")

        assert all("【イントラネット】" in record.getMessage() for record in caplog.records)

    def test_failure_is_logged_with_elapsed_time_and_reraised(self, fake_clock, caplog) -> None:
        def main() -> None:
            fake_clock["now"] += 125
            raise RuntimeError("失敗")

        with caplog.at_level(logging.INFO, logger="comken.run"), pytest.raises(RuntimeError):
            run.backoffice(main, "売上集計")

        failure = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert [r.getMessage() for r in failure] == [
            "【バックオフィス】売上集計 が異常終了しました（実行時間 00:02）"
        ]
