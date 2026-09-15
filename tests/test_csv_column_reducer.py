"""comken/services/csv_column_reducer の列削減（reduce_columns / reduce_ouju_csv_file）のテスト。"""

import pytest

from comken.core import Table
from comken.exceptions import TableColumnNotFoundError, TableError
from comken.services.csv_column_reducer import reduce_columns
from comken.services.csv_column_reducer.file_ops import reduce_ouju_csv_file
from comken.services.csv_column_reducer.ouju_role import reduce_ouju_csv
from comken.toolbox.csv import CSV


class TestReduceColumns:
    """reduce_columns() — 欲しい列名とリネーム対応表による選択。"""

    def test_selects_only_requested_columns_in_requested_order(self):
        """欲しい列だけを、指定した順番で残す。"""
        table = Table(["a", "b", "c"], [{"a": "1", "b": "2", "c": "3"}])

        result = reduce_columns(table, ["c", "a"])

        assert result.columns == ["c", "a"]
        assert result.to_rows() == [{"c": "3", "a": "1"}]

    def test_absorbs_renamed_columns_via_aliases(self):
        """新ロールでリネームされた列も、aliasesで指定すれば旧名で取り出せる。"""
        table = Table(["顧客ID", "氏名"], [{"顧客ID": "001", "氏名": "山田"}])

        result = reduce_columns(table, ["顧客番号", "氏名"], aliases={"顧客番号": "顧客ID"})

        assert result.columns == ["顧客番号", "氏名"]
        assert result.to_rows() == [{"顧客番号": "001", "氏名": "山田"}]

    def test_raises_when_requested_column_is_missing(self):
        """欲しい列（aliasesで解決した実名を含む）がtableに無ければ例外。"""
        table = Table(["a"], [{"a": "1"}])

        with pytest.raises(TableColumnNotFoundError):
            reduce_columns(table, ["b"])

    def test_type_converters_follow_the_renamed_column(self):
        """types で指定した変換は、リネーム後の列名にもついてくる。"""
        table = Table(["顧客ID"], [{"顧客ID": "1"}], types={"顧客ID": int})

        result = reduce_columns(table, ["顧客番号"], aliases={"顧客番号": "顧客ID"})

        assert result.to_rows() == [{"顧客番号": 1}]


class TestReduceOujuCsv:
    """reduce_ouju_csv() — columns省略時はOLD_ROLE_COLUMNSを使う。"""

    def test_uses_explicit_columns_instead_of_default(self, monkeypatch):
        """columnsを渡すと、既定のOLD_ROLE_COLUMNSではなくそちらを使う。"""
        import comken.services.csv_column_reducer.ouju_role as ouju_role_module

        monkeypatch.setattr(ouju_role_module, "OLD_ROLE_COLUMNS", ["z"])
        table = Table(["a", "z"], [{"a": "1", "z": "2"}])

        result = reduce_ouju_csv(table, columns=["a"])

        assert result.columns == ["a"]

    def test_falls_back_to_old_role_columns_when_omitted(self, monkeypatch):
        """columns省略時は、その時点のOLD_ROLE_COLUMNSを使う。"""
        import comken.services.csv_column_reducer.ouju_role as ouju_role_module

        monkeypatch.setattr(ouju_role_module, "OLD_ROLE_COLUMNS", ["a"])
        table = Table(["a", "b"], [{"a": "1", "b": "2"}])

        result = reduce_ouju_csv(table)

        assert result.columns == ["a"]

    def test_absorbs_asterisk_that_was_added_in_new_role(self, monkeypatch):
        """新ロールで先頭に＊が付いた列も、旧ロール名で自動的に拾う。"""
        import comken.services.csv_column_reducer.ouju_role as ouju_role_module

        monkeypatch.setattr(ouju_role_module, "OLD_ROLE_COLUMNS", ["氏名"])
        table = Table(["＊氏名"], [{"＊氏名": "山田"}])

        result = reduce_ouju_csv(table)

        assert result.to_rows() == [{"氏名": "山田"}]

    def test_absorbs_asterisk_that_was_removed_in_new_role(self, monkeypatch):
        """旧ロールで＊付きだった列が新ロールで＊なしになっても拾う。"""
        import comken.services.csv_column_reducer.ouju_role as ouju_role_module

        monkeypatch.setattr(ouju_role_module, "OLD_ROLE_COLUMNS", ["＊住所"])
        table = Table(["住所"], [{"住所": "名古屋"}])

        result = reduce_ouju_csv(table)

        assert result.to_rows() == [{"＊住所": "名古屋"}]

    def test_exact_match_is_preferred_over_asterisk_normalization(self, monkeypatch):
        """完全一致する列があれば、＊正規化ではなくそちらをそのまま使う。"""
        import comken.services.csv_column_reducer.ouju_role as ouju_role_module

        monkeypatch.setattr(ouju_role_module, "OLD_ROLE_COLUMNS", ["氏名"])
        table = Table(["氏名", "＊氏名"], [{"氏名": "本物", "＊氏名": "別列"}])

        result = reduce_ouju_csv(table)

        assert result.to_rows() == [{"氏名": "本物"}]


class TestReduceOujuCsvFile:
    """reduce_ouju_csv_file() — 削減成功後にだけ元ファイルをバックアップへ複製し、
    同名で書き戻す。
    """

    def test_backs_up_original_and_writes_reduced_csv_with_same_name(self, tmp_path, monkeypatch):
        import comken.services.csv_column_reducer.ouju_role as ouju_role_module

        monkeypatch.setattr(ouju_role_module, "OLD_ROLE_COLUMNS", ["a"])
        path = tmp_path / "応需.csv"
        path.write_text("a,b\n1,2\n", encoding="utf-8-sig")

        backup_path = reduce_ouju_csv_file(path)

        assert backup_path == tmp_path / "応需_bak.csv"
        assert backup_path.exists()
        with CSV(backup_path, read_only=True) as backup_csv:
            assert backup_csv.read().columns == ["a", "b"]
        with CSV(path, read_only=True) as reduced_csv:
            assert reduced_csv.read() == [{"a": "1"}]

    def test_overwrites_columns_argument_when_given(self, tmp_path, monkeypatch):
        import comken.services.csv_column_reducer.ouju_role as ouju_role_module

        monkeypatch.setattr(ouju_role_module, "OLD_ROLE_COLUMNS", ["a"])
        path = tmp_path / "応需.csv"
        path.write_text("a,b\n1,2\n", encoding="utf-8-sig")

        reduce_ouju_csv_file(path, columns=["b"])

        with CSV(path, read_only=True) as reduced_csv:
            assert reduced_csv.read() == [{"b": "2"}]

    def test_original_file_is_untouched_when_reduction_fails(self, tmp_path, monkeypatch):
        """欲しい列が無くて削減に失敗しても、元ファイル・バックアップともに触らない。

        （リトライのたびに直前の正常なバックアップを潰してしまう事故を防ぐため。
        失敗時は元ファイルがそのまま残るので、設定を直して同じファイルへ再実行できる）。
        """
        import comken.services.csv_column_reducer.ouju_role as ouju_role_module

        monkeypatch.setattr(ouju_role_module, "OLD_ROLE_COLUMNS", ["存在しない列"])
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
        import comken.services.csv_column_reducer.ouju_role as ouju_role_module

        monkeypatch.setattr(ouju_role_module, "OLD_ROLE_COLUMNS", ["存在しない列"])
        path = tmp_path / "応需.csv"
        path.write_text("a,b\n1,2\n", encoding="utf-8-sig")
        with pytest.raises(TableColumnNotFoundError):
            reduce_ouju_csv_file(path)

        monkeypatch.setattr(ouju_role_module, "OLD_ROLE_COLUMNS", ["a"])
        backup_path = reduce_ouju_csv_file(path)

        assert backup_path.exists()
        with CSV(path, read_only=True) as reduced_csv:
            assert reduced_csv.read() == [{"a": "1"}]

    def test_duplicate_old_role_columns_raise_before_touching_files(self, tmp_path, monkeypatch):
        """OLD_ROLE_COLUMNSに重複があれば、Tableの検証でそのまま例外になる。

        （専用の重複チェックを別途書かなくても、Tableのコンストラクタが
        列名の重複を拒否するため、ここでも自然にカバーされる）。
        """
        import comken.services.csv_column_reducer.ouju_role as ouju_role_module

        monkeypatch.setattr(ouju_role_module, "OLD_ROLE_COLUMNS", ["a", "a"])
        path = tmp_path / "応需.csv"
        original_content = "a,b\n1,2\n"
        path.write_text(original_content, encoding="utf-8-sig")

        with pytest.raises(TableError):
            reduce_ouju_csv_file(path)

        assert path.read_text(encoding="utf-8-sig") == original_content
