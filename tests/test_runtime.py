"""
runtime（version / デバッグモード / dry-run）のテスト。
"""

import logging

import pytest

import comken
from comken.core.files import move_file
from comken.core.timer import measure
from comken.toolbox.csv.writer import CsvWriter


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
        from comken.toolbox.csv import CsvReader

        path = tmp_path / "data.csv"
        path.write_text("番号\n1\n", encoding="utf-8-sig")
        with comken.debug(), caplog.at_level(logging.DEBUG):
            CsvReader(path).read_rows()

        assert "rows" in caplog.text

    def test_nested_and_exception_restore_previous_state(self):
        """入れ子と例外の後に、入る前の状態へ戻る。"""
        assert not comken.is_debug()
        with pytest.raises(RuntimeError), comken.debug():
            assert comken.is_debug()
            with comken.debug(False):
                assert not comken.is_debug()
            assert comken.is_debug()
            raise RuntimeError
        assert not comken.is_debug()


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
        assert "[DRY-RUN]" in caplog.text

    def test_csv_writer_skipped(self, tmp_path, caplog):
        """dry-run 中は CSV が書き込まれないことを確認する。"""
        path = tmp_path / "out.csv"
        with comken.dry_run(), caplog.at_level(logging.INFO):
            CsvWriter(path, fieldnames=["番号"]).write_rows([{"番号": "1"}])

        assert not path.exists()
        assert "[DRY-RUN]" in caplog.text

    def test_excel_save_skipped(self, tmp_path, caplog):
        """dry-run 中は Excel が保存されないことを確認する。"""
        from comken.toolbox.excel import ExcelWriter

        path = tmp_path / "out.xlsx"
        with comken.dry_run(), caplog.at_level(logging.INFO), ExcelWriter.create(path) as f:
            f.sheet("Sheet1")["A1"] = "test"
            f.save()

        assert not path.exists()
        assert "[DRY-RUN]" in caplog.text

    def test_reads_still_work(self, tmp_path):
        """dry-run 中でも読み取りは通常どおり実行されることを確認する。"""
        from comken.toolbox.csv import CsvReader

        path = tmp_path / "data.csv"
        path.write_text("番号\n1\n", encoding="utf-8-sig")
        with comken.dry_run():
            assert CsvReader(path).read_rows() == [{"番号": "1"}]

    def test_nested_and_exception_restore_previous_state(self):
        """入れ子と例外の後に、入る前の状態へ戻る。"""
        assert not comken.is_dry_run()
        with pytest.raises(RuntimeError), comken.dry_run():
            assert comken.is_dry_run()
            with comken.dry_run():
                assert comken.is_dry_run()
            raise RuntimeError
        assert not comken.is_dry_run()

    def test_false_temporarily_allows_writes(self, tmp_path):
        """外側が dry-run でも dry_run(False) 内は通常どおり書き込む。"""
        path = tmp_path / "out.csv"
        with comken.dry_run():
            with comken.dry_run(False):
                CsvWriter(path, fieldnames=["番号"]).write_rows([{"番号": "1"}])
            assert comken.is_dry_run()
        assert path.exists()


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


# ---------------------------------------------------------------------------
# 環境変数 / setter によるモード切替（v0.12.0 で追加）
# ---------------------------------------------------------------------------

import comken.runtime as _runtime  # noqa: E402  — 末尾に置く


@pytest.fixture(autouse=True)
def _reset_runtime_overrides(monkeypatch):
    """各テストの前後で override と環境変数を初期状態へ戻す。

    環境変数を unset すると「未設定 → False」が確実に確認できる。
    override は内部の _dry_run_override / _debug_override を直接 None へ戻す
    （テスト間で値が漏れないように）。
    """
    monkeypatch.delenv("COMKEN_DRY_RUN", raising=False)
    monkeypatch.delenv("COMKEN_DEBUG", raising=False)
    _runtime._dry_run_override = None
    _runtime._debug_override = None
    yield
    _runtime._dry_run_override = None
    _runtime._debug_override = None


class TestDryRunFromEnv:
    """環境変数 COMKEN_DRY_RUN による dry-run 解決。"""

    def test_default_is_false(self):
        """環境変数未設定 + オーバーライドなし → False。"""
        assert comken.is_dry_run() is False

    def test_env_1_is_true(self, monkeypatch):
        """COMKEN_DRY_RUN=1 で True。"""
        monkeypatch.setenv("COMKEN_DRY_RUN", "1")
        assert comken.is_dry_run() is True

    def test_env_0_is_false(self, monkeypatch):
        """COMKEN_DRY_RUN=0 で False（"0" は真とみなさない）。"""
        monkeypatch.setenv("COMKEN_DRY_RUN", "0")
        assert comken.is_dry_run() is False

    def test_env_true_yes_on(self, monkeypatch):
        """COMKEN_DRY_RUN=true / yes / on を True 扱い。"""
        for value in ["true", "yes", "on", "TRUE", "Yes", "ON"]:
            monkeypatch.setenv("COMKEN_DRY_RUN", value)
            assert comken.is_dry_run() is True, f"expected True for {value!r}"

    def test_env_empty_is_false(self, monkeypatch):
        """空文字は False 扱い（「設定はあるが off」）。"""
        monkeypatch.setenv("COMKEN_DRY_RUN", "")
        assert comken.is_dry_run() is False

    def test_env_unknown_value_is_false(self, monkeypatch):
        """真とみなす集合以外は False。"""
        monkeypatch.setenv("COMKEN_DRY_RUN", "maybe")
        assert comken.is_dry_run() is False


class TestDryRunSetter:
    """set_dry_run と context manager による上書き。"""

    def test_set_true_overrides_env(self, monkeypatch):
        """set_dry_run(True) は環境変数の False を上書きする。"""
        monkeypatch.setenv("COMKEN_DRY_RUN", "0")
        _runtime.set_dry_run(True)
        assert comken.is_dry_run() is True

    def test_set_false_overrides_env(self, monkeypatch):
        """set_dry_run(False) は環境変数の True を上書きする。"""
        monkeypatch.setenv("COMKEN_DRY_RUN", "1")
        _runtime.set_dry_run(False)
        assert comken.is_dry_run() is False

    def test_set_none_returns_to_env(self, monkeypatch):
        """set_dry_run(None) で解除し、以降は環境変数に従う。"""
        monkeypatch.setenv("COMKEN_DRY_RUN", "1")
        _runtime.set_dry_run(True)  # 真の値を一時的に設定
        _runtime.set_dry_run(None)  # 解除
        assert comken.is_dry_run() is True  # 環境変数 (1) が生きる

    def test_set_none_returns_to_default_when_env_unset(self):
        """set_dry_run(None) で解除、環境変数未設定なら False。"""
        _runtime.set_dry_run(True)
        _runtime.set_dry_run(None)
        assert comken.is_dry_run() is False

    def test_context_manager_restores_previous(self):
        """with dry_run() を抜けたら元の状態（unset → 環境変数）に戻る。"""
        assert comken.is_dry_run() is False
        with comken.dry_run():
            assert comken.is_dry_run() is True
        assert comken.is_dry_run() is False

    def test_context_manager_restores_setter_value(self, monkeypatch):
        """外側で set_dry_run(True) した状態を、with 抜けた後に復元。"""
        monkeypatch.setenv("COMKEN_DRY_RUN", "0")
        _runtime.set_dry_run(True)
        with comken.dry_run(False):
            assert comken.is_dry_run() is False
        # ブロック前の setter (True) に戻る
        assert comken.is_dry_run() is True
        # setter を解除すると環境変数の False が効く
        _runtime.set_dry_run(None)
        assert comken.is_dry_run() is False

    def test_context_manager_restores_on_exception(self):
        """ブロック内で例外が出ても元の状態へ戻る。"""
        assert comken.is_dry_run() is False
        with pytest.raises(RuntimeError), comken.dry_run():
            assert comken.is_dry_run() is True
            raise RuntimeError
        assert comken.is_dry_run() is False

    def test_nested_context_managers(self):
        """入れ子の context manager が内側→外側の順に復元する。"""
        assert comken.is_dry_run() is False
        with comken.dry_run():
            assert comken.is_dry_run() is True
            with comken.dry_run(False):
                assert comken.is_dry_run() is False
            assert comken.is_dry_run() is True
        assert comken.is_dry_run() is False


class TestDebugFromEnv:
    """環境変数 COMKEN_DEBUG による debug 解決。"""

    def test_default_is_false(self):
        """環境変数未設定 + オーバーライドなし → False。"""
        assert comken.is_debug() is False

    def test_env_1_is_true(self, monkeypatch):
        """COMKEN_DEBUG=1 で True。"""
        monkeypatch.setenv("COMKEN_DEBUG", "1")
        assert comken.is_debug() is True

    def test_env_true_yes_on(self, monkeypatch):
        """COMKEN_DEBUG=true / yes / on を True 扱い。"""
        for value in ["true", "yes", "on"]:
            monkeypatch.setenv("COMKEN_DEBUG", value)
            assert comken.is_debug() is True, f"expected True for {value!r}"

    def test_env_zero_is_false(self, monkeypatch):
        """COMKEN_DEBUG=0 は False。"""
        monkeypatch.setenv("COMKEN_DEBUG", "0")
        assert comken.is_debug() is False


class TestDebugSetter:
    """set_debug と context manager による上書き。"""

    def test_set_true_overrides_env(self, monkeypatch):
        """set_debug(True) は環境変数を上書き。"""
        monkeypatch.setenv("COMKEN_DEBUG", "0")
        _runtime.set_debug(True)
        assert comken.is_debug() is True

    def test_set_none_returns_to_env(self, monkeypatch):
        """set_debug(None) で解除し、以降は環境変数に従う。"""
        monkeypatch.setenv("COMKEN_DEBUG", "1")
        _runtime.set_debug(False)
        _runtime.set_debug(None)
        assert comken.is_debug() is True

    def test_context_manager_restores_previous(self):
        """with debug() を抜けたら元の状態に戻る。"""
        assert comken.is_debug() is False
        with comken.debug():
            assert comken.is_debug() is True
        assert comken.is_debug() is False

    def test_context_manager_restores_on_exception(self):
        """ブロック内で例外が出ても元の状態へ戻る。"""
        assert comken.is_debug() is False
        with pytest.raises(RuntimeError), comken.debug():
            assert comken.is_debug() is True
            raise RuntimeError
        assert comken.is_debug() is False


class TestPackageReExports:
    """新 setter は comken.runtime 配下に置く（facade は少数のまま保つ方針）。"""

    def test_set_dry_run_lives_in_runtime_module(self):
        """comken.runtime.set_dry_run が callable。"""
        assert callable(_runtime.set_dry_run)

    def test_set_debug_lives_in_runtime_module(self):
        """comken.runtime.set_debug が callable。"""
        assert callable(_runtime.set_debug)
