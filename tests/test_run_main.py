"""comken.runtime.run_main のテスト。

``run_main`` は ``main.py`` の定型（dry-run / debug の with 囲み、
``ComkenError`` の捕捉と終了コード化、想定外例外の再送出）を 1 か所に
まとめるヘルパー。確認点は次のとおり。

- ``main()`` が想定どおり呼ばれる
- 戻り値が ``int`` のときそのまま、``None`` のとき ``0``
- ``ComkenError`` を ``logger.error`` で受け止めて ``1``
- 想定外の ``Exception`` は ``logger.exception`` の後そのまま再送出
- ``debug_mode=True`` のとき呼び出し中だけ ``is_debug() == True``
- ``dry_run_mode=True`` のとき呼び出し中だけ ``is_dry_run() == True``
- 実行後に状態が漏れない
"""

import logging

import pytest

from comken.exceptions import ComkenError, ConfigError
from comken.runtime import is_debug, is_dry_run, run_main


class TestSuccessExitCode:
    def test_none_return_is_zero(self) -> None:
        """main() の戻り値が None のときは 0。"""

        def main() -> None:
            return None

        assert run_main(main) == 0

    def test_int_return_passes_through(self) -> None:
        """main() の戻り値が int のときはそのまま返す。"""

        def main() -> int:
            return 7

        assert run_main(main) == 7

    def test_runs_without_state_leak(self) -> None:
        """実行後に dry_run / debug 状態が漏れない。"""

        def main() -> None:
            return None

        assert is_dry_run() is False
        assert is_debug() is False
        run_main(main)
        assert is_dry_run() is False
        assert is_debug() is False


class TestComkenError:
    def test_returns_one_and_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        """``ComkenError`` で止まったときは ``logger.error`` して 1 を返す。"""

        def main() -> None:
            raise ConfigError("SAMPLE_KEY 不在")

        with caplog.at_level(logging.ERROR):
            result = run_main(main)

        assert result == 1
        assert "処理を中断しました" in caplog.text
        assert "SAMPLE_KEY 不在" in caplog.text

    def test_category_base_also_caught(self, caplog: pytest.LogCaptureFixture) -> None:
        """カテゴリ基底 (``ConfigError`` 等) も ``ComkenError`` と同じく 1 で受け止める。"""

        def main() -> None:
            raise ConfigError("ini が壊れています")

        with caplog.at_level(logging.ERROR):
            result = run_main(main)

        assert result == 1
        assert "処理を中断しました" in caplog.text

    def test_base_itself_also_caught(self) -> None:
        """``ComkenError`` の直系派生（基底そのもの）でも 1 で受け止める。"""

        def main() -> None:
            raise ComkenError("基底エラー")

        assert run_main(main) == 1


class TestUnexpectedException:
    def test_reraises_after_logger_exception(self, caplog: pytest.LogCaptureFixture) -> None:
        """想定外例外は ``logger.exception`` した上でそのまま送出する。"""

        sentinel = RuntimeError("想定外")

        def main() -> None:
            raise sentinel

        with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError, match="想定外"):
            run_main(main)

        assert "予期しないエラーが発生しました" in caplog.text


class TestModeFlags:
    def test_dry_run_mode_makes_is_dry_run_true_inside(self) -> None:
        """``dry_run_mode=True`` のときは main の中で ``is_dry_run()`` が True。

        main の外では False に戻る（状態の漏れがない）。
        """
        observed: list[tuple[bool, bool]] = []

        def main() -> None:
            observed.append((is_dry_run(), is_debug()))

        assert is_dry_run() is False
        run_main(main, dry_run_mode=True)
        assert is_dry_run() is False
        assert observed == [(True, False)]

    def test_debug_mode_makes_is_debug_true_inside(self) -> None:
        """``debug_mode=True`` のときは main の中で ``is_debug()`` が True。"""
        observed: list[tuple[bool, bool]] = []

        def main() -> None:
            observed.append((is_dry_run(), is_debug()))

        assert is_debug() is False
        run_main(main, debug_mode=True)
        assert is_debug() is False
        assert observed == [(False, True)]

    def test_both_modes_active_together(self) -> None:
        """両方を True にしても両方の状態が同時に True になる（順序の確認）。"""
        observed: list[tuple[bool, bool]] = []

        def main() -> None:
            observed.append((is_dry_run(), is_debug()))

        run_main(main, debug_mode=True, dry_run_mode=True)

        assert observed == [(True, True)]
        assert is_dry_run() is False
        assert is_debug() is False

    def test_no_modes_leaves_state_off(self) -> None:
        """``debug_mode=False`` / ``dry_run_mode=False`` のときは main の中でも False。"""
        observed: list[tuple[bool, bool]] = []

        def main() -> None:
            observed.append((is_dry_run(), is_debug()))

        run_main(main)
        assert observed == [(False, False)]


class TestExceptionDoesNotLeakState:
    """``ComkenError`` / 想定外例外の後でも状態は元に戻る。"""

    def test_comken_error_restores_mode_state(self) -> None:
        def main() -> None:
            raise ConfigError("error")

        assert is_dry_run() is False
        assert is_debug() is False
        run_main(main, debug_mode=True, dry_run_mode=True)
        assert is_dry_run() is False
        assert is_debug() is False
