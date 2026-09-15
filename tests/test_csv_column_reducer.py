"""comken/services/csv_column_reducer（応需CSVの新ロール→旧ロール列削減）のテスト。

列選択そのもの（aliasesによる列名ゆれの吸収）は Table.select() 側の契約なので
tests/test_new_table_api.py で確認する。ファイル読み書き・バックアップの
骨格は transform_csv_file() 側の契約なので tests/test_csv_transform_file.py
で確認する。ここでは応需固有の部分（*吸収・OLD_ROLE_COLUMNSとの配線）だけを見る。
"""

from comken.core import Table
from comken.services.csv_column_reducer import reduce_ouju_csv
from comken.toolbox.csv import transform_csv_file


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


def test_transform_csv_file_composes_with_reduce_ouju_csv(tmp_path, monkeypatch):
    """csv_column_reducer.py のdocstringに載せた使い方どおり、そのまま組み合わせて動く。"""
    import comken.services.csv_column_reducer as csv_column_reducer_module

    monkeypatch.setattr(csv_column_reducer_module, "OLD_ROLE_COLUMNS", ["a"])
    path = tmp_path / "応需.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8-sig")

    transform_csv_file(path, reduce_ouju_csv)

    assert path.read_text(encoding="utf-8-sig") == "a\n1\n"
