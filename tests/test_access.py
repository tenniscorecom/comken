"""Access COM 操作の配線をモックで検証する。"""

import inspect
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from comken import dry_run
from comken.access import AccessDatabase
from comken.constants import Encoding
from comken.exceptions import (
    AccessLocalCopyError,
    AccessSourceNotFoundError,
    UnsupportedFileSuffixError,
)


def _database(tmp_path: Path) -> tuple[AccessDatabase, MagicMock]:
    path = tmp_path / "顧客.accdb"
    path.touch()
    access = MagicMock()
    with patch("comken.access.handler.win32com.client.DispatchEx", return_value=access):
        database = AccessDatabase(path, local_copy=False)
    return database, access


def _set_sources(access: MagicMock, tables: list[str], queries: list[str] | None = None) -> None:
    queries = queries or []
    access.CurrentData.AllTables.Count = len(tables)
    access.CurrentData.AllQueries.Count = len(queries)
    access.CurrentData.AllTables.Item.side_effect = [MagicMock(Name=name) for name in tables]
    access.CurrentData.AllQueries.Item.side_effect = [MagicMock(Name=name) for name in queries]


class TestAccessDatabase:
    def test_default_opens_local_copy_and_removes_it(self, tmp_path):
        path = tmp_path / "顧客.accdb"
        path.write_bytes(b"database")
        access = MagicMock()

        with (
            patch("comken.access.handler.win32com.client.DispatchEx", return_value=access),
            AccessDatabase(path) as database,
        ):
            opened_path = Path(access.OpenCurrentDatabase.call_args.args[0])
            assert opened_path != path.resolve()
            assert opened_path.suffix == path.suffix
            assert opened_path.read_bytes() == b"database"
            assert database.path == path

        assert not opened_path.exists()

    def test_exception_removes_local_copy_and_lock_file(self, tmp_path):
        path = tmp_path / "顧客.accdb"
        path.touch()
        original_lock = tmp_path / "顧客.laccdb"
        original_lock.write_text("元のロック", encoding="utf-8")
        access = MagicMock()

        with (
            patch("comken.access.handler.win32com.client.DispatchEx", return_value=access),
            pytest.raises(RuntimeError),
            AccessDatabase(path),
        ):
            opened_path = Path(access.OpenCurrentDatabase.call_args.args[0])
            lock_path = opened_path.with_suffix(".laccdb")
            lock_path.write_text("コピー側のロック", encoding="utf-8")
            raise RuntimeError("test")

        assert not opened_path.exists()
        assert not lock_path.exists()
        assert original_lock.read_text(encoding="utf-8") == "元のロック"

    def test_local_copy_false_opens_original_without_copy(self, tmp_path):
        path = tmp_path / "顧客.accdb"
        path.touch()
        access = MagicMock()

        with (
            patch("comken.access.handler.win32com.client.DispatchEx", return_value=access),
            AccessDatabase(path, local_copy=False),
        ):
            pass

        access.OpenCurrentDatabase.assert_called_once_with(str(path.resolve()))
        assert list(tmp_path.iterdir()) == [path]

    def test_local_copy_logs_that_changes_are_not_reflected(self, tmp_path, caplog):
        path = tmp_path / "顧客.accdb"
        path.touch()

        with (
            patch("comken.access.handler.win32com.client.DispatchEx", return_value=MagicMock()),
            caplog.at_level(logging.INFO, logger="comken.access.handler"),
            AccessDatabase(path),
        ):
            pass

        assert "元のデータベースへの変更は反映されません" in caplog.text

    def test_copy_failure_raises_access_error(self, tmp_path):
        path = tmp_path / "顧客.accdb"
        path.touch()

        with (
            patch("comken.access.handler.shutil.copy2", side_effect=PermissionError("使用中")),
            pytest.raises(AccessLocalCopyError, match="読み取り権限"),
        ):
            AccessDatabase(path)

    def test_run_macro_calls_do_cmd(self, tmp_path):
        database, access = _database(tmp_path)
        database.run_macro("日次整形")
        access.DoCmd.RunMacro.assert_called_once_with("日次整形")

    def test_run_function_calls_application_run(self, tmp_path):
        database, access = _database(tmp_path)
        database.run_function("集計", 1, "A")
        access.Run.assert_called_once_with("集計", 1, "A")

    def test_export_csv_calls_transfer_text(self, tmp_path):
        database, access = _database(tmp_path)
        _set_sources(access, ["T_出力"])
        target = tmp_path / "out.csv"
        database.export_csv("T_出力", target, Encoding.CP932)
        access.DoCmd.TransferText.assert_called_once_with(
            2, "", "T_出力", str(target.resolve()), True, "", 932
        )

    def test_rows_is_generator_and_reads_batches(self, tmp_path):
        database, access = _database(tmp_path)
        _set_sources(access, ["T_出力"])
        recordset = access.CurrentDb.return_value.OpenRecordset.return_value
        recordset.Fields.Count = 2
        recordset.Fields.Item.side_effect = [MagicMock(Name="ID"), MagicMock(Name="名前")]
        recordset.EOF = False
        recordset.GetRows.side_effect = [((1, 2), ("A", "B")), ()]
        rows = database.rows("T_出力")
        assert inspect.isgenerator(rows)
        assert list(rows) == [{"ID": 1, "名前": "A"}, {"ID": 2, "名前": "B"}]
        recordset.GetRows.assert_called_with(1000)
        recordset.Close.assert_called_once()

    def test_missing_source_lists_existing_names(self, tmp_path):
        database, access = _database(tmp_path)
        _set_sources(access, ["T_顧客"], ["Q_出力"])
        with pytest.raises(AccessSourceNotFoundError, match=r"T_顧客.*Q_出力"):
            database.export_csv("T_なし", tmp_path / "out.csv")

    def test_dry_run_skips_external_operations(self, tmp_path):
        database, access = _database(tmp_path)
        _set_sources(access, ["T_出力"])
        with dry_run():
            database.run_macro("日次整形")
            database.run_function("集計")
            database.export_csv("T_出力", tmp_path / "out.csv")
        access.DoCmd.RunMacro.assert_not_called()
        access.Run.assert_not_called()
        access.DoCmd.TransferText.assert_not_called()

    def test_context_manager_quits_after_exception(self, tmp_path):
        database, access = _database(tmp_path)
        with pytest.raises(RuntimeError), database:
            raise RuntimeError("test")
        access.Quit.assert_called_once()

    @pytest.mark.parametrize("suffix", [".xlsx", ".csv"])
    def test_unsupported_suffix(self, tmp_path, suffix):
        with pytest.raises(UnsupportedFileSuffixError):
            AccessDatabase(tmp_path / f"data{suffix}")
