"""comken/services/csv_column_reducer（応需CSVの新ロール→旧ロール列削減）のテスト。

列選択そのもの（aliasesによる列名ゆれの吸収）は Table.select() 側の契約なので
tests/test_new_table_api.py で確認する。ここでは応需固有の部分
（*吸収・OLD_ROLE_COLUMNSとの配線・ファイル入出力）を見る。
"""

import pytest

from comken.core import Table
from comken.exceptions import CSVError, TableColumnNotFoundError
from comken.services.csv_column_reducer import (
    reduce_ouju_csv,
    reduce_ouju_csv_file,
    reduce_ouju_csv_folder,
)
from comken.toolbox.csv import CSV


class TestReduceOujuCsv:
    """reduce_ouju_csv() — columns省略時はOLD_ROLE_COLUMNSを使う。"""

    def test_uses_explicit_columns_instead_of_default(self, monkeypatch):
        """columnsを渡すと、既定のOLD_ROLE_COLUMNSではなくそちらを使う。"""
        import comken.services.csv_column_reducer as csv_column_reducer_module

        monkeypatch.setattr(csv_column_reducer_module, "OLD_ROLE_COLUMNS", ["z"])
        table = Table(["a", "z"], [{"a": "1", "z": "2"}])

        result = reduce_ouju_csv(table, columns=["a"])

        assert result.columns == ["a"]

    def test_falls_back_to_old_role_columns_when_omitted(self, monkeypatch):
        """columns省略時は、その時点のOLD_ROLE_COLUMNSを使う。"""
        import comken.services.csv_column_reducer as csv_column_reducer_module

        monkeypatch.setattr(csv_column_reducer_module, "OLD_ROLE_COLUMNS", ["a"])
        table = Table(["a", "b"], [{"a": "1", "b": "2"}])

        result = reduce_ouju_csv(table)

        assert result.columns == ["a"]

    def test_absorbs_asterisk_that_was_added_in_new_role(self, monkeypatch):
        """新ロールで先頭に*が付いた列も、旧ロール名で自動的に拾う。"""
        import comken.services.csv_column_reducer as csv_column_reducer_module

        monkeypatch.setattr(csv_column_reducer_module, "OLD_ROLE_COLUMNS", ["氏名"])
        table = Table(["*氏名"], [{"*氏名": "山田"}])

        result = reduce_ouju_csv(table)

        assert result.to_rows() == [{"氏名": "山田"}]

    def test_absorbs_asterisk_that_was_removed_in_new_role(self, monkeypatch):
        """旧ロールで*付きだった列が新ロールで*なしになっても拾う。"""
        import comken.services.csv_column_reducer as csv_column_reducer_module

        monkeypatch.setattr(csv_column_reducer_module, "OLD_ROLE_COLUMNS", ["*住所"])
        table = Table(["住所"], [{"住所": "名古屋"}])

        result = reduce_ouju_csv(table)

        assert result.to_rows() == [{"*住所": "名古屋"}]

    def test_exact_match_is_preferred_over_asterisk_normalization(self, monkeypatch):
        """完全一致する列があれば、*正規化ではなくそちらをそのまま使う。"""
        import comken.services.csv_column_reducer as csv_column_reducer_module

        monkeypatch.setattr(csv_column_reducer_module, "OLD_ROLE_COLUMNS", ["氏名"])
        table = Table(["氏名", "*氏名"], [{"氏名": "本物", "*氏名": "別列"}])

        result = reduce_ouju_csv(table)

        assert result.to_rows() == [{"氏名": "本物"}]


class TestReduceOujuCsvFile:
    """reduce_ouju_csv_file() — 削減成功後にだけ元ファイルをバックアップへ複製し、
    同名で書き戻す。
    """

    def test_backs_up_original_and_writes_reduced_csv_with_same_name(self, tmp_path, monkeypatch):
        import comken.services.csv_column_reducer as csv_column_reducer_module

        monkeypatch.setattr(csv_column_reducer_module, "OLD_ROLE_COLUMNS", ["a"])
        path = tmp_path / "応需.csv"
        path.write_text("a,b\n1,2\n", encoding="utf-8-sig")

        backup_path = reduce_ouju_csv_file(path)

        assert backup_path == tmp_path / "応需_bak.csv"
        assert backup_path.exists()
        with CSV(backup_path, read_only=True) as backup_csv:
            assert backup_csv.read().columns == ["a", "b"]
        with CSV(path, read_only=True) as reduced_csv:
            assert reduced_csv.read() == [{"a": "1"}]

    def test_columns_argument_overrides_old_role_columns(self, tmp_path, monkeypatch):
        import comken.services.csv_column_reducer as csv_column_reducer_module

        monkeypatch.setattr(csv_column_reducer_module, "OLD_ROLE_COLUMNS", ["a"])
        path = tmp_path / "応需.csv"
        path.write_text("a,b\n1,2\n", encoding="utf-8-sig")

        reduce_ouju_csv_file(path, columns=["b"])

        with CSV(path, read_only=True) as reduced_csv:
            assert reduced_csv.read() == [{"b": "2"}]

    def test_backup_suffix_argument_is_passed_through(self, tmp_path, monkeypatch):
        import comken.services.csv_column_reducer as csv_column_reducer_module

        monkeypatch.setattr(csv_column_reducer_module, "OLD_ROLE_COLUMNS", ["a"])
        path = tmp_path / "応需.csv"
        path.write_text("a,b\n1,2\n", encoding="utf-8-sig")

        backup_path = reduce_ouju_csv_file(path, backup_suffix="_old")

        assert backup_path == tmp_path / "応需_old.csv"

    def test_original_file_is_untouched_when_reduction_fails(self, tmp_path, monkeypatch):
        """欲しい列が無くて削減に失敗しても、元ファイル・バックアップともに触らない。

        （リトライのたびに直前の正常なバックアップを潰してしまう事故を防ぐため。
        失敗時は元ファイルがそのまま残るので、設定を直して同じファイルへ再実行できる）。
        """
        import comken.services.csv_column_reducer as csv_column_reducer_module

        monkeypatch.setattr(csv_column_reducer_module, "OLD_ROLE_COLUMNS", ["存在しない列"])
        path = tmp_path / "応需.csv"
        original_content = "a,b\n1,2\n"
        path.write_text(original_content, encoding="utf-8-sig")

        with pytest.raises(TableColumnNotFoundError):
            reduce_ouju_csv_file(path)

        assert path.read_text(encoding="utf-8-sig") == original_content
        assert not (tmp_path / "応需_bak.csv").exists()

    def test_retry_after_fixing_config_succeeds_without_losing_previous_backup(
        self, tmp_path, monkeypatch
    ):
        """1回目が失敗しても、設定を直せば同じファイルへ再実行できる。

        （先にリネームしてから削減する順序だと、1回目の失敗時点で元ファイルが
        既に無くなっているため、この再実行自体ができなかった）。
        """
        import comken.services.csv_column_reducer as csv_column_reducer_module

        monkeypatch.setattr(csv_column_reducer_module, "OLD_ROLE_COLUMNS", ["存在しない列"])
        path = tmp_path / "応需.csv"
        path.write_text("a,b\n1,2\n", encoding="utf-8-sig")
        with pytest.raises(TableColumnNotFoundError):
            reduce_ouju_csv_file(path)

        monkeypatch.setattr(csv_column_reducer_module, "OLD_ROLE_COLUMNS", ["a"])
        backup_path = reduce_ouju_csv_file(path)

        assert backup_path.exists()
        with CSV(path, read_only=True) as reduced_csv:
            assert reduced_csv.read() == [{"a": "1"}]


class TestReduceOujuCsvFolder:
    """フォルダ内・ドラッグ＆ドロップで渡した CSV を、まとめて旧ロールの列に絞る。"""

    def _write(self, path, text="a,b,c\n1,2,3\n"):
        path.write_text(text, encoding="utf-8-sig")
        return path

    def test_converts_every_csv_in_the_folder_and_keeps_full_backups(self, tmp_path):
        self._write(tmp_path / "一.csv")
        self._write(tmp_path / "二.csv")

        backups = reduce_ouju_csv_folder(tmp_path, columns=["a", "b"])

        assert sorted(p.name for p in backups) == ["一_bak.csv", "二_bak.csv"]
        for name in ("一", "二"):
            with CSV(tmp_path / f"{name}.csv", read_only=True) as reduced:
                assert reduced.read().columns == ["a", "b"]
            with CSV(tmp_path / f"{name}_bak.csv", read_only=True) as backup:
                assert backup.read().columns == ["a", "b", "c"]

    def test_second_run_does_not_overwrite_the_full_column_backup(self, tmp_path):
        """2回実行しても、新ロールのバックアップ（全列）が、絞った内容で上書きされない。"""
        self._write(tmp_path / "応需.csv")
        reduce_ouju_csv_folder(tmp_path, columns=["a", "b"])

        second = reduce_ouju_csv_folder(tmp_path, columns=["a", "b"])

        assert second == []  # すでに旧ロールの列だけなので飛ばした
        with CSV(tmp_path / "応需_bak.csv", read_only=True) as backup:
            assert backup.read().columns == ["a", "b", "c"]

    def test_a_newly_downloaded_file_with_the_same_name_is_converted_again(self, tmp_path):
        """同じ名前で新しくダウンロードした（全列の）CSV は、もう一度変換される。"""
        self._write(tmp_path / "応需.csv")
        reduce_ouju_csv_folder(tmp_path, columns=["a", "b"])
        self._write(tmp_path / "応需.csv", "a,b,c\n7,8,9\n")

        backups = reduce_ouju_csv_folder(tmp_path, columns=["a", "b"])

        assert [p.name for p in backups] == ["応需_bak.csv"]
        with CSV(tmp_path / "応需_bak.csv", read_only=True) as backup:
            assert backup.read().to_rows() == [{"a": "7", "b": "8", "c": "9"}]

    def test_backup_files_are_skipped(self, tmp_path):
        self._write(tmp_path / "応需_bak.csv")

        assert reduce_ouju_csv_folder(tmp_path, columns=["a", "b"]) == []
        with CSV(tmp_path / "応需_bak.csv", read_only=True) as untouched:
            assert untouched.read().columns == ["a", "b", "c"]

    def test_one_bad_file_does_not_stop_the_others(self, tmp_path):
        """欲しい列が無いファイルがあっても、残りは変換し、最後にまとめて知らせる。"""
        self._write(tmp_path / "ok.csv")
        self._write(tmp_path / "bad.csv", "x,y\n1,2\n")

        with pytest.raises(CSVError, match=r"bad.csv"):
            reduce_ouju_csv_folder(tmp_path, columns=["a", "b"])

        with CSV(tmp_path / "ok.csv", read_only=True) as converted:
            assert converted.read().columns == ["a", "b"]
        with CSV(tmp_path / "bad.csv", read_only=True) as untouched:
            assert untouched.read().columns == ["x", "y"]  # 失敗したファイルは元のまま
        assert not (tmp_path / "bad_bak.csv").exists()


class TestMain:
    """``python -m`` の入口。ファイル・フォルダの両方を受け取る（bat へのドラッグ＆ドロップ）。"""

    def _write(self, path):
        path.write_text("a,b,c\n1,2,3\n", encoding="utf-8-sig")

    def test_dropped_files_only_are_converted(self, tmp_path, monkeypatch):
        import comken.services.csv_column_reducer as module

        monkeypatch.setattr(module, "OLD_ROLE_COLUMNS", ["a", "b"])
        self._write(tmp_path / "対象.csv")
        self._write(tmp_path / "対象外.csv")

        module.main([str(tmp_path / "対象.csv")])

        with CSV(tmp_path / "対象.csv", read_only=True) as converted:
            assert converted.read().columns == ["a", "b"]
        with CSV(tmp_path / "対象外.csv", read_only=True) as untouched:
            assert untouched.read().columns == ["a", "b", "c"]

    def test_dropped_folder_converts_the_csv_files_inside(self, tmp_path, monkeypatch):
        import comken.services.csv_column_reducer as module

        monkeypatch.setattr(module, "OLD_ROLE_COLUMNS", ["a", "b"])
        self._write(tmp_path / "応需.csv")

        module.main([str(tmp_path)])

        with CSV(tmp_path / "応需.csv", read_only=True) as converted:
            assert converted.read().columns == ["a", "b"]

    def test_no_arguments_uses_the_current_folder(self, tmp_path, monkeypatch):
        import comken.services.csv_column_reducer as module

        monkeypatch.setattr(module, "OLD_ROLE_COLUMNS", ["a", "b"])
        monkeypatch.chdir(tmp_path)
        self._write(tmp_path / "応需.csv")

        module.main([])

        with CSV(tmp_path / "応需.csv", read_only=True) as converted:
            assert converted.read().columns == ["a", "b"]

    def test_failure_exits_with_code_1_so_the_bat_can_notice(self, tmp_path, monkeypatch):
        import comken.services.csv_column_reducer as module

        monkeypatch.setattr(module, "OLD_ROLE_COLUMNS", ["a", "b"])
        (tmp_path / "bad.csv").write_text("x,y\n1,2\n", encoding="utf-8-sig")

        with pytest.raises(SystemExit) as caught:
            module.main([str(tmp_path)])

        assert caught.value.code == 1
