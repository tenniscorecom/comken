"""comken.toolbox.csv.transform_csv_file() のテスト。

「transform が先、バックアップは成功後にだけ作る」という順序を確かめる
（失敗時に直前の正常なバックアップを潰してしまう事故を防ぐための順序）。
"""

import pytest

from comken.core import Table
from comken.exceptions import TableColumnNotFoundError
from comken.toolbox.csv import CSV, transform_csv_file


def _select_a(table: Table) -> Table:
    return table.select("a")


def _always_fails(table: Table) -> Table:
    raise TableColumnNotFoundError(["存在しない列"])


class TestTransformCsvFile:
    def test_backs_up_original_and_writes_transformed_csv_with_same_name(self, tmp_path):
        path = tmp_path / "data.csv"
        path.write_text("a,b\n1,2\n", encoding="utf-8-sig")

        backup_path = transform_csv_file(path, _select_a)

        assert backup_path == tmp_path / "data_bak.csv"
        assert backup_path.exists()
        with CSV(backup_path, read_only=True) as backup_csv:
            assert backup_csv.read().columns == ["a", "b"]
        with CSV(path, read_only=True) as transformed_csv:
            assert transformed_csv.read() == [{"a": "1"}]

    def test_custom_backup_suffix(self, tmp_path):
        path = tmp_path / "data.csv"
        path.write_text("a,b\n1,2\n", encoding="utf-8-sig")

        backup_path = transform_csv_file(path, _select_a, backup_suffix="_old")

        assert backup_path == tmp_path / "data_old.csv"

    def test_original_file_is_untouched_when_transform_fails(self, tmp_path):
        """transform が失敗しても、元ファイル・バックアップともに触らない。

        （リトライのたびに直前の正常なバックアップを潰してしまう事故を防ぐため。
        失敗時は元ファイルがそのまま残るので、設定を直して同じファイルへ再実行できる）。
        """
        path = tmp_path / "data.csv"
        original_content = "a,b\n1,2\n"
        path.write_text(original_content, encoding="utf-8-sig")

        with pytest.raises(TableColumnNotFoundError):
            transform_csv_file(path, _always_fails)

        assert path.read_text(encoding="utf-8-sig") == original_content
        assert not (tmp_path / "data_bak.csv").exists()

    def test_retry_after_fixing_transform_succeeds(self, tmp_path):
        """1回目が失敗しても、transformを直せば同じファイルへ再実行できる。

        （先にリネームしてからtransformする順序だと、1回目の失敗時点で
        元ファイルが既に無くなっているため、この再実行自体ができなかった）。
        """
        path = tmp_path / "data.csv"
        path.write_text("a,b\n1,2\n", encoding="utf-8-sig")

        with pytest.raises(TableColumnNotFoundError):
            transform_csv_file(path, _always_fails)

        backup_path = transform_csv_file(path, _select_a)

        assert backup_path.exists()
        with CSV(path, read_only=True) as transformed_csv:
            assert transformed_csv.read() == [{"a": "1"}]

    def test_overwrites_existing_backup(self, tmp_path):
        """既に同名のバックアップがあれば上書きする（直前の成功時点の複製のため）。"""
        path = tmp_path / "data.csv"
        path.write_text("a,b\n1,2\n", encoding="utf-8-sig")
        backup_path = tmp_path / "data_bak.csv"
        backup_path.write_text("old,stale\nX,Y\n", encoding="utf-8-sig")

        transform_csv_file(path, _select_a)

        with CSV(backup_path, read_only=True) as backup_csv:
            assert backup_csv.read().columns == ["a", "b"]
