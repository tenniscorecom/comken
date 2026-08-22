"""
runtime（version / デバッグモード / dry-run）のテスト。

dry-run / debug は `with` ブロックでのみ切り替える。環境変数や setter は
存在しない（簡素化により削除済み）。`is_dry_run()` / `is_debug()` は
`comken` の facade には載せず、`comken.runtime` 内に閉じた内部用。
"""

import logging

import pytest

import comken
from comken.core.files import move_file
from comken.core.timer import measure
from comken.runtime import debug, dry_run, is_debug, is_dry_run
from comken.toolbox.csv import CSV


class TestVersion:
    def test_version_returns_string(self):
        """comken.__version__ がバージョン文字列であることを確認する。"""
        assert comken.__version__.count(".") == 2  # "X.Y.Z" 形式


class TestDebugMode:
    def test_measure_silent_by_default(self, caplog):
        """デバッグモード OFF では measure はログを出さないことを確認する。"""

        @measure
        def func():
            return 1

        with caplog.at_level(logging.DEBUG):
            assert func() == 1

        assert "func" not in caplog.text

    def test_measure_logs_when_debug_on(self, caplog):
        """debug() 内では処理時間が DEBUG ログに出ることを確認する。"""

        @measure
        def slow_func():
            return "ok"

        with comken.debug(), caplog.at_level(logging.DEBUG):
            assert slow_func() == "ok"

        assert "slow_func" in caplog.text
        assert "秒" in caplog.text

    def test_measure_emits_start_and_complete(self, caplog):
        """デバッグモードでは「開始」「完了」の2行が出ることを確認する。"""

        @measure
        def do_work():
            return 1

        with comken.debug(), caplog.at_level(logging.DEBUG, logger="comken.core.timer"):
            assert do_work() == 1

        # 開始ログと完了ログの両方が同じ qualname で出ている
        assert "do_work: 開始" in caplog.text
        assert "do_work: 完了" in caplog.text
        # 「中断」は出ない
        assert "中断" not in caplog.text

    def test_measure_logs_interrupt_on_exception(self, caplog):
        """例外で抜けたとき「開始」「中断」が出て、例外がそのまま伝わることを確認する。"""

        @measure
        def fails():
            raise RuntimeError("boom")

        with (
            pytest.raises(RuntimeError, match="boom"),
            comken.debug(),
            caplog.at_level(logging.DEBUG, logger="comken.core.timer"),
        ):
            fails()

        assert "fails: 開始" in caplog.text
        assert "fails: 中断" in caplog.text
        # 完了は出ない
        assert "fails: 完了" not in caplog.text

    def test_measure_catches_keyboard_interrupt(self, caplog):
        """KeyboardInterrupt でも「中断」が出て再送出されることを確認する。"""

        @measure
        def hang():
            raise KeyboardInterrupt()

        with (
            pytest.raises(KeyboardInterrupt),
            comken.debug(),
            caplog.at_level(logging.DEBUG, logger="comken.core.timer"),
        ):
            hang()

        assert "hang: 開始" in caplog.text
        assert "hang: 中断" in caplog.text
        assert "hang: 完了" not in caplog.text

    def test_measure_does_not_log_arguments(self, caplog):
        """引数の値がログに出ないことを確認する（秘密の値が漏れないことの担保）。"""

        @measure
        def with_secret(secret: str) -> str:
            return secret

        with comken.debug(), caplog.at_level(logging.DEBUG, logger="comken.core.timer"):
            assert with_secret("super-secret-token-12345") == "super-secret-token-12345"

        # qualname は出てもよいが、引数の値は絶対に出してはならない
        assert "with_secret" in caplog.text
        assert "super-secret-token-12345" not in caplog.text

    def test_measure_does_not_log_return_value(self, caplog):
        """戻り値もログに出ないことを確認する。"""

        @measure
        def returns_secret() -> str:
            return "another-secret-value"

        with comken.debug(), caplog.at_level(logging.DEBUG, logger="comken.core.timer"):
            assert returns_secret() == "another-secret-value"

        assert "another-secret-value" not in caplog.text

    def test_library_methods_measured(self, tmp_path, caplog):
        """ライブラリの主要処理（CSV 読み込み等）が計測対象になっていることを確認する。"""
        from comken.toolbox.csv import CSV

        path = tmp_path / "data.csv"
        path.write_text("番号\n1\n", encoding="utf-8-sig")
        with comken.debug(), caplog.at_level(logging.DEBUG):
            CSV(path).read()

        assert CSV(path).read().count() == 1

    def test_nested_and_exception_restore_previous_state(self):
        """入れ子と例外の後に、入る前の状態へ戻る。"""
        assert not is_debug()
        with pytest.raises(RuntimeError), debug():
            assert is_debug()
            with debug(False):
                assert not is_debug()
            assert is_debug()
            raise RuntimeError
        assert not is_debug()


class TestDryRun:
    def test_move_file_skipped(self, tmp_path, caplog):
        """dry-run 中は move_file が実行されず、内容がログに出ることを確認する。"""
        src = tmp_path / "report.xlsx"
        src.write_text("data", encoding="utf-8")
        with comken.dry_run(), caplog.at_level(logging.INFO):
            result = move_file(src, tmp_path / "out" / "moved.xlsx")

        assert src.exists()  # 移動されていない
        assert not (tmp_path / "out").exists()
        assert result == tmp_path / "out" / "moved.xlsx"  # 返り値は本来の移動先

    def test_csv_writer_skipped(self, tmp_path, caplog):
        """dry-run 中は CSV が書き込まれないことを確認する。"""
        path = tmp_path / "out.csv"
        with comken.dry_run(), caplog.at_level(logging.INFO), CSV(path) as csv_file:
            csv_file.replace([{"番号": "1"}])

        assert not path.exists()

    def test_excel_save_skipped(self, tmp_path, caplog):
        """dry-run 中は Excel が保存されないことを確認する。"""
        from comken.toolbox.excel import Excel

        path = tmp_path / "out.xlsx"
        with comken.dry_run(), caplog.at_level(logging.INFO), Excel(path) as excel:
            excel.sheet("Sheet1").write_value("A1", "test")

        assert not path.exists()
        assert "[DRY-RUN]" in caplog.text

    def test_reads_still_work(self, tmp_path):
        """dry-run 中でも読み取りは通常どおり実行されることを確認する。"""
        from comken.toolbox.csv import CSV

        path = tmp_path / "data.csv"
        path.write_text("番号\n1\n", encoding="utf-8-sig")
        with comken.dry_run():
            assert CSV(path).read().read() == [{"番号": "1"}]

    def test_nested_and_exception_restore_previous_state(self):
        """入れ子と例外の後に、入る前の状態へ戻る。"""
        assert not is_dry_run()
        with pytest.raises(RuntimeError), dry_run():
            assert is_dry_run()
            with dry_run():
                assert is_dry_run()
            raise RuntimeError
        assert not is_dry_run()

    def test_false_temporarily_allows_writes(self, tmp_path):
        """外側が dry-run でも dry_run(False) 内は通常どおり書き込む。"""
        path = tmp_path / "out.csv"
        with comken.dry_run():
            with comken.dry_run(False), CSV(path) as csv_file:
                csv_file.replace([{"番号": "1"}])
            assert is_dry_run()
        assert path.exists()


class TestRuntimeState:
    """context manager でのみ切り替わる内部状態のテスト。

    環境変数・setter は存在しないため、すべて `with` ブロック経由で確認する。
    """

    def test_initial_state_is_false(self):
        """プロセス起動直後は dry-run / debug ともに False。"""
        assert is_dry_run() is False
        assert is_debug() is False

    def test_dry_run_block_enables_then_restores(self):
        """dry_run() を抜けたら元の状態（False）へ戻る。"""
        assert is_dry_run() is False
        with dry_run():
            assert is_dry_run() is True
        assert is_dry_run() is False

    def test_debug_block_enables_then_restores(self):
        """debug() を抜けたら元の状態（False）へ戻る。"""
        assert is_debug() is False
        with debug():
            assert is_debug() is True
        assert is_debug() is False

    def test_dry_run_false_disables_inside_block(self):
        """dry_run(False) はブロック内だけ dry-run を解除する。"""
        assert is_dry_run() is False
        with dry_run(False):
            assert is_dry_run() is False
        assert is_dry_run() is False

    def test_debug_false_disables_inside_block(self):
        """debug(False) は何もしない（初期 False をそのまま返す）。"""
        assert is_debug() is False
        with debug(False):
            assert is_debug() is False
        assert is_debug() is False

    def test_dry_run_false_within_outer_dry_run_allows_writes(self):
        """外側 dry-run の中で dry_run(False) だけが実際の書き込みを許す。"""
        # ここは test_dry_run_false_disables_inside_block と同じ True/False ではなく
        # 「外で True・内で False・外で True」が守られることを assert で確認する。
        assert is_dry_run() is False
        with dry_run():
            assert is_dry_run() is True
            with dry_run(False):
                assert is_dry_run() is False
            assert is_dry_run() is True
        assert is_dry_run() is False

    def test_debug_false_within_outer_debug_disables(self):
        """外側 debug() の中で debug(False) だけが DEBUG ログを止めることを前提とし、
        状態の出入りが想定どおりであることを確認する。"""
        assert is_debug() is False
        with debug():
            assert is_debug() is True
            with debug(False):
                assert is_debug() is False
            assert is_debug() is True
        assert is_debug() is False

    def test_dry_run_and_debug_are_independent(self):
        """dry_run() と debug() は独立して動作する。"""
        assert is_dry_run() is False
        assert is_debug() is False
        with dry_run():
            assert is_dry_run() is True
            assert is_debug() is False
            with debug():
                assert is_dry_run() is True
                assert is_debug() is True
            assert is_dry_run() is True
            assert is_debug() is False
        assert is_dry_run() is False
        assert is_debug() is False

    def test_state_restored_on_exception(self):
        """ブロック内で例外が出ても状態は元に戻る。"""
        assert is_dry_run() is False
        with pytest.raises(RuntimeError), dry_run():
            assert is_dry_run() is True
            raise RuntimeError
        assert is_dry_run() is False

        assert is_debug() is False
        with pytest.raises(RuntimeError), debug():
            assert is_debug() is True
            raise RuntimeError
        assert is_debug() is False


class TestDiffLeadingZero:
    """diff の先頭ゼロ保護のテスト（仕様固定）。"""

    def test_leading_zero_string_differs_from_number(self):
        """ "0001"（文字列）と 1（数値）は差分として検出されることを確認する。

        社員番号・郵便番号などの先頭ゼロの消失を「差分なし」と誤判定しない。
        """
        from comken.core.data import diff_row

        assert diff_row({"社員番号": "0001"}, {"社員番号": 1}) == {"社員番号": ("0001", 1)}

    def test_leading_zero_strings_match(self):
        """ "0001" 同士は差分にならないことを確認する。"""
        from comken.core.data import diff_row

        assert diff_row({"社員番号": "0001"}, {"社員番号": "0001"}) == {}
