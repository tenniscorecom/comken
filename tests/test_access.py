"""Access COM 操作の配線をモックで検証する。"""

import inspect
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from comken import dry_run
from comken.constants import Encoding
from comken.exceptions import (
    AccessBackupError,
    AccessLocalCopyError,
    AccessSourceNotFoundError,
    UnsupportedFileSuffixError,
)
from comken.toolbox.access import AccessDatabase


def _database(tmp_path: Path) -> tuple[AccessDatabase, MagicMock]:
    path = tmp_path / "顧客.accdb"
    path.touch()
    access = MagicMock()
    with patch("comken.toolbox.access.handler.win32com.client.DispatchEx", return_value=access):
        database = AccessDatabase(path, local_copy=False, backup=False)
    return database, access


def _set_sources(access: MagicMock, tables: list[str], queries: list[str] | None = None) -> None:
    queries = queries or []
    access.CurrentData.AllTables.Count = len(tables)
    access.CurrentData.AllQueries.Count = len(queries)
    access.CurrentData.AllTables.Item.side_effect = lambda index: MagicMock(Name=tables[index])
    access.CurrentData.AllQueries.Item.side_effect = lambda index: MagicMock(Name=queries[index])


class TestAccessDatabase:
    def test_default_opens_local_copy_and_removes_it(self, tmp_path):
        path = tmp_path / "顧客.accdb"
        path.write_bytes(b"database")
        access = MagicMock()

        with (
            patch("comken.toolbox.access.handler.win32com.client.DispatchEx", return_value=access),
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
            patch("comken.toolbox.access.handler.win32com.client.DispatchEx", return_value=access),
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
            patch("comken.toolbox.access.handler.win32com.client.DispatchEx", return_value=access),
            AccessDatabase(path, local_copy=False, backup=False),
        ):
            pass

        access.OpenCurrentDatabase.assert_called_once_with(str(path.resolve()))
        assert list(tmp_path.iterdir()) == [path]

    def test_local_copy_false_backs_up_before_opening(self, tmp_path):
        path = tmp_path / "顧客.accdb"
        path.write_bytes(b"database")
        backup_folder = tmp_path / "backup"
        access = MagicMock()

        def assert_backup_exists(_database_path):
            backups = list(backup_folder.glob("*.accdb"))
            assert len(backups) == 1
            assert backups[0].read_bytes() == b"database"

        access.OpenCurrentDatabase.side_effect = assert_backup_exists
        with (
            patch("comken.toolbox.access.handler.win32com.client.DispatchEx", return_value=access),
            AccessDatabase(path, local_copy=False, backup_dir=backup_folder),
        ):
            pass

    def test_default_local_copy_does_not_back_up(self, tmp_path):
        path = tmp_path / "顧客.accdb"
        path.touch()
        backup_folder = tmp_path / "backups"
        with (
            patch(
                "comken.toolbox.access.handler.win32com.client.DispatchEx", return_value=MagicMock()
            ),
            AccessDatabase(path, backup_dir=backup_folder),
        ):
            pass
        assert not backup_folder.exists()

    def test_backup_false_does_not_back_up(self, tmp_path):
        path = tmp_path / "顧客.accdb"
        path.touch()
        backup_folder = tmp_path / "backups"
        with (
            patch(
                "comken.toolbox.access.handler.win32com.client.DispatchEx", return_value=MagicMock()
            ),
            AccessDatabase(path, local_copy=False, backup=False, backup_dir=backup_folder),
        ):
            pass
        assert not backup_folder.exists()

    def test_backups_in_same_second_are_not_overwritten(self, tmp_path):
        path = tmp_path / "顧客.accdb"
        path.write_bytes(b"database")
        backup_folder = tmp_path / "backups"
        fixed_now = datetime(2026, 7, 29, 15, 30, 45, tzinfo=UTC)
        for _ in range(2):
            with (
                patch("comken.toolbox.access.handler.now", return_value=fixed_now),
                patch("comken.core.utils.files.naming.date.now", return_value=fixed_now),
                patch(
                    "comken.toolbox.access.handler.win32com.client.DispatchEx",
                    return_value=MagicMock(),
                ),
                AccessDatabase(path, local_copy=False, backup_dir=backup_folder),
            ):
                pass
        assert sorted(item.name for item in backup_folder.iterdir()) == [
            "20260729_153045_顧客.accdb",
            "20260729_153045_顧客_2.accdb",
        ]

    def test_removes_only_expired_backups_for_same_database(self, tmp_path, caplog):
        path = tmp_path / "顧客.accdb"
        path.touch()
        backup_folder = tmp_path / "backups"
        backup_folder.mkdir()
        old_same = backup_folder / "20260701_120000_顧客.accdb"
        recent_same = backup_folder / "20260729_120000_顧客.accdb"
        old_other = backup_folder / "20260701_120000_顧客台帳.accdb"
        for item in (old_same, recent_same, old_other):
            item.touch()
        fixed_now = datetime(2026, 7, 29, 15, 30, 45, tzinfo=UTC)
        old_timestamp = (fixed_now - timedelta(days=8)).timestamp()
        recent_timestamp = (fixed_now - timedelta(days=1)).timestamp()
        os.utime(old_same, (old_timestamp, old_timestamp))
        os.utime(old_other, (old_timestamp, old_timestamp))
        os.utime(recent_same, (recent_timestamp, recent_timestamp))

        with (
            patch("comken.toolbox.access.handler.now", return_value=fixed_now),
            patch("comken.core.utils.files.naming.date.now", return_value=fixed_now),
            patch(
                "comken.toolbox.access.handler.win32com.client.DispatchEx", return_value=MagicMock()
            ),
            caplog.at_level(logging.INFO, logger="comken.toolbox.access.handler"),
            AccessDatabase(path, local_copy=False, backup_dir=backup_folder),
        ):
            pass

        assert not old_same.exists()
        assert recent_same.exists()
        assert old_other.exists()
        assert "7日分残す設定に従い、期限切れの控えを1件削除しました" in caplog.text

    def test_backup_failure_does_not_open_database(self, tmp_path):
        path = tmp_path / "顧客.accdb"
        path.touch()
        access = MagicMock()
        with (
            patch(
                "comken.toolbox.access.handler.shutil.copy2", side_effect=PermissionError("拒否")
            ),
            patch("comken.toolbox.access.handler.win32com.client.DispatchEx", return_value=access),
            pytest.raises(AccessBackupError, match="更新を中止"),
        ):
            AccessDatabase(path, local_copy=False, backup_dir=tmp_path / "backup")
        access.OpenCurrentDatabase.assert_not_called()

    def test_backup_folder_creation_failure_does_not_open_database(self, tmp_path):
        path = tmp_path / "顧客.accdb"
        path.touch()
        access = MagicMock()
        with (
            patch("comken.toolbox.access.handler.Path.mkdir", side_effect=PermissionError("拒否")),
            patch("comken.toolbox.access.handler.win32com.client.DispatchEx", return_value=access),
            pytest.raises(AccessBackupError, match=r"backup_dir.*ローカルフォルダ"),
        ):
            AccessDatabase(path, local_copy=False)
        access.OpenCurrentDatabase.assert_not_called()

    def test_lock_file_warns_during_backup(self, tmp_path, caplog):
        path = tmp_path / "顧客.accdb"
        path.touch()
        path.with_suffix(".laccdb").touch()
        with (
            patch(
                "comken.toolbox.access.handler.win32com.client.DispatchEx", return_value=MagicMock()
            ),
            caplog.at_level(logging.WARNING, logger="comken.toolbox.access.handler"),
            AccessDatabase(path, local_copy=False, backup_dir=tmp_path / "backup"),
        ):
            pass
        assert "他の利用者が Access を開いている状態" in caplog.text

    def test_dry_run_skips_backup(self, tmp_path):
        path = tmp_path / "顧客.accdb"
        path.touch()
        backup_folder = tmp_path / "backups"
        with (
            dry_run(),
            patch(
                "comken.toolbox.access.handler.win32com.client.DispatchEx", return_value=MagicMock()
            ),
            AccessDatabase(path, local_copy=False, backup_dir=backup_folder),
        ):
            pass
        assert not backup_folder.exists()

    def test_default_backup_folder_is_next_to_database(self, monkeypatch, tmp_path):
        current_folder = tmp_path / "current"
        database_folder = tmp_path / "shared"
        current_folder.mkdir()
        database_folder.mkdir()
        monkeypatch.chdir(current_folder)
        path = database_folder / "顧客.accdb"
        path.write_bytes(b"database")

        with (
            patch(
                "comken.toolbox.access.handler.win32com.client.DispatchEx", return_value=MagicMock()
            ),
            AccessDatabase(path, local_copy=False),
        ):
            pass

        backups = list((database_folder / "backup").glob("*.accdb"))
        assert len(backups) == 1
        assert not (current_folder / "backup").exists()

    def test_local_copy_logs_that_changes_are_not_reflected(self, tmp_path, caplog):
        path = tmp_path / "顧客.accdb"
        path.touch()

        with (
            patch(
                "comken.toolbox.access.handler.win32com.client.DispatchEx", return_value=MagicMock()
            ),
            caplog.at_level(logging.INFO, logger="comken.toolbox.access.handler"),
            AccessDatabase(path),
        ):
            pass

        assert "元のデータベースへの変更は反映されません" in caplog.text

    def test_copy_failure_raises_access_error(self, tmp_path):
        path = tmp_path / "顧客.accdb"
        path.touch()

        with (
            patch(
                "comken.toolbox.access.handler.shutil.copy2", side_effect=PermissionError("使用中")
            ),
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

    def test_run_query_executes_saved_query_by_name(self, tmp_path):
        database, access = _database(tmp_path)
        _set_sources(access, [], ["Q_日次更新"])

        database.run_query("Q_日次更新")

        access.CurrentDb.return_value.QueryDefs.return_value.Execute.assert_called_once_with(128)

    def test_run_query_rejects_unknown_query(self, tmp_path):
        database, access = _database(tmp_path)
        _set_sources(access, [], ["Q_日次更新"])

        with pytest.raises(AccessSourceNotFoundError, match=r"Q_なし.*Q_日次更新"):
            database.run_query("Q_なし")

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
        rows = database.read_rows("T_出力")
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
        _set_sources(access, ["T_出力"], ["Q_更新"])
        with dry_run():
            database.run_macro("日次整形")
            database.run_function("集計")
            database.run_query("Q_更新")
            database.export_csv("T_出力", tmp_path / "out.csv")
        access.DoCmd.RunMacro.assert_not_called()
        access.Run.assert_not_called()
        access.CurrentDb.return_value.QueryDefs.assert_not_called()
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
