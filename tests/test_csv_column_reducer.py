"""comken/services/csv_column_reducer の列削減（reduce_columns / reduce_ouju_csv_file）のテスト。"""

import pytest

from comken.core import Table
from comken.exceptions import TableColumnNotFoundError
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


class TestReduceOujuCsvFile:
    """reduce_ouju_csv_file() — 元ファイルをバックアップへ退避し、同名で書き戻す。"""

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
