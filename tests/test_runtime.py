"""
runtime（version / デバッグモード / dry-run）のテスト。
"""

import logging

import pytest

import comken
from comken.csv.writer import CsvWriter
from comken.utils import measure
from comken.utils.files import move_file


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

    def test_library_methods_measured(self, tmp_path, caplog):
        """ライブラリの主要処理（CSV 読み込み等）が計測対象になっていることを確認する。"""
        from comken.csv import CsvReader

        path = tmp_path / "data.csv"
        path.write_text("番号\n1\n", encoding="utf-8-sig")
        with comken.debug(), caplog.at_level(logging.DEBUG):
            CsvReader(path).rows()

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
        from comken.excel import ExcelWriter

        path = tmp_path / "out.xlsx"
        with comken.dry_run(), caplog.at_level(logging.INFO), ExcelWriter.create(path) as f:
            f.sheet("Sheet1")["A1"] = "test"
            f.save()

        assert not path.exists()
        assert "[DRY-RUN]" in caplog.text

    def test_reads_still_work(self, tmp_path):
        """dry-run 中でも読み取りは通常どおり実行されることを確認する。"""
        from comken.csv import CsvReader

        path = tmp_path / "data.csv"
        path.write_text("番号\n1\n", encoding="utf-8-sig")
        with comken.dry_run():
            assert CsvReader(path).rows() == [{"番号": "1"}]

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
        from comken.utils import diff_row

        assert diff_row({"社員番号": "0001"}, {"社員番号": 1}) == {"社員番号": ("0001", 1)}

    def test_leading_zero_strings_match(self):
        """ "0001" 同士は差分にならないことを確認する。"""
        from comken.utils import diff_row

        assert diff_row({"社員番号": "0001"}, {"社員番号": "0001"}) == {}
