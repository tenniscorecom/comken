"""Microsoft Access のマクロ実行・データ出力。"""

import logging
import os
import re
import shutil
import tempfile
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import win32com.client

from ..constants import Encoding
from ..exceptions import (
    AccessBackupError,
    AccessFileNotFoundError,
    AccessLocalCopyError,
    AccessRoutineError,
    AccessSourceNotFoundError,
)
from ..runtime import dry_run_log, is_dry_run
from ..utils.clock import now
from ..utils.files.base import FileBase
from ..utils.files.naming import DateNameBuilder

logger = logging.getLogger(__name__)

ACCESS_EXPORT_DELIMITED = 2
ACCESS_OPEN_TABLE = 0
ACCESS_OPEN_QUERY = 1
CP932_CODE_PAGE = 932
UTF8_CODE_PAGE = 65001
ROWS_BATCH_SIZE = 1000
DEFAULT_BACKUP_DAYS = 7
BACKUP_DATE_FORMAT = "%Y%m%d_%H%M%S"
BACKUP_FOLDER_NAME = "access-backup"
_ENCODING_CODE_PAGES = {
    Encoding.CP932: CP932_CODE_PAGE,
    Encoding.UTF8_SIG: UTF8_CODE_PAGE,
}


class AccessDatabase(FileBase):
    """Access データベースを COM で操作する。

    既定ではネットワーク越しの遅延・排他・破損を避けるため、一時フォルダへコピーして開く。
    コピー上の変更は元ファイルへ反映されない。元データベースを更新するマクロを実行する場合は
    ``local_copy=False`` を指定する。この場合は開く前に日時付きバックアップを作り、
    既定で7日間残す。バックアップは成功後も削除せず、自動では書き戻さない。
    復旧時は内容を確認した人が手でコピーする（自動復旧は正常なデータを古い控えで
    上書きする危険があるため）。

    数十万件を CSV に出す場合は、Python にデータを載せない ``export_csv()`` を使う。
    ``rows()`` は逐次処理用であり、結果を ``list`` にすると全件分のメモリを消費する。
    """

    SUFFIXES = (".accdb", ".mdb")

    def __init__(
        self,
        path: str | Path,
        local_copy: bool = True,
        backup: bool | None = None,
        backup_days: int = DEFAULT_BACKUP_DAYS,
    ) -> None:
        super().__init__(path)
        if not self.path.is_file():
            raise AccessFileNotFoundError(self.path)
        if backup_days < 0:
            raise ValueError("backup_days は0以上で指定してください。")

        self._working_path = self._path
        self._temporary_directory: tempfile.TemporaryDirectory[str] | None = None
        self._access = None
        should_backup = not local_copy if backup is None else backup

        if should_backup:
            self._backup(backup_days)
        elif not is_dry_run():
            backup_folder = _backup_folder()
            if backup_folder.is_dir():
                _remove_expired_backups(backup_folder, self._path, backup_days)

        if local_copy:
            self._temporary_directory = tempfile.TemporaryDirectory(prefix="comken_access_")
            self._working_path = (
                Path(self._temporary_directory.name) / f"database{self._path.suffix}"
            )
            try:
                shutil.copy2(self._path, self._working_path)
            except Exception as e:
                self._temporary_directory.cleanup()
                self._temporary_directory = None
                raise AccessLocalCopyError(self._path, e) from e

        # DispatchEx は利用者が手で開いている Access とは別のプロセスを起動する。
        try:
            self._access = win32com.client.DispatchEx("Access.Application")
            self._access.Visible = False
            self._access.OpenCurrentDatabase(str(self._working_path.resolve()))
        except Exception:
            self._close()
            raise
        if local_copy:
            logger.info(
                "Access ファイルをローカルにコピーして開きました。"
                "元のデータベースへの変更は反映されません: %s",
                self._path,
            )

    def __enter__(self) -> "AccessDatabase":
        return self

    def __exit__(self, *args: object) -> None:
        self._close()

    def run_macro(self, name: str) -> None:
        """Access マクロを実行する。

        元データベースを更新するマクロの場合は、初期化時に ``local_copy=False`` を指定する。
        VBA のプロシージャ／関数を実行する場合は ``run_function()`` を使う。
        """
        if is_dry_run():
            dry_run_log("Access マクロを実行: %s（%s）", name, self.path)
            return
        try:
            self._access.DoCmd.RunMacro(name)
        except Exception as e:
            raise AccessRoutineError(name, "マクロ", e) from e

    def run_function(self, name: str, *args: object) -> object | None:
        """VBA のプロシージャ／関数を実行する。

        元データベースを更新する処理の場合は、初期化時に ``local_copy=False`` を指定する。
        Access のマクロは別の仕組みなので、マクロには ``run_macro()`` を使う。
        dry-run 時は実行せず ``None`` を返す。
        """
        if is_dry_run():
            dry_run_log("Access VBA を実行: %s%r（%s）", name, args, self.path)
            return None
        try:
            return self._access.Run(name, *args)
        except Exception as e:
            raise AccessRoutineError(name, "VBA", e) from e

    def export_csv(
        self,
        source: str,
        dst: str | Path,
        encoding: str = Encoding.CP932,
    ) -> None:
        """テーブルまたはクエリを Access から直接 CSV に書き出す。

        数十万件でも Python のメモリにデータを載せない、大量件数向けの方法。
        """
        self._ensure_source(source)
        try:
            code_page = _ENCODING_CODE_PAGES[encoding]
        except KeyError as e:
            choices = list(_ENCODING_CODE_PAGES)
            raise ValueError(f"encoding は次から指定してください: {choices}") from e
        destination = Path(dst)
        if is_dry_run():
            dry_run_log("Access「%s」を CSV に出力: %s", source, destination)
            return
        self._access.DoCmd.TransferText(
            ACCESS_EXPORT_DELIMITED,
            "",
            source,
            str(destination.resolve()),
            True,
            "",
            code_page,
        )

    def rows(self, source: str) -> Iterator[dict[str, object]]:
        """テーブルまたはクエリを辞書で1行ずつ返すジェネレータ。

        COM 往復を減らすため小さなバッチで取得する。数十万件を ``list`` にすると
        メモリを大量に使うため、CSV が目的なら ``export_csv()`` を使う。
        """
        self._ensure_source(source)
        recordset = self._access.CurrentDb().OpenRecordset(source)
        try:
            field_names = [
                str(recordset.Fields.Item(index).Name) for index in range(recordset.Fields.Count)
            ]
            while not recordset.EOF:
                columns = recordset.GetRows(ROWS_BATCH_SIZE)
                if not columns:
                    break
                for values in zip(*columns, strict=True):
                    yield dict(zip(field_names, values, strict=True))
        finally:
            recordset.Close()

    def table_names(self) -> list[str]:
        """利用可能なテーブルと保存済みクエリの名前を返す。"""
        current_data = self._access.CurrentData
        tables = []
        for index in range(current_data.AllTables.Count):
            name = str(current_data.AllTables.Item(index).Name)
            if not name.startswith("MSys"):
                tables.append(name)
        queries = [
            str(current_data.AllQueries.Item(index).Name)
            for index in range(current_data.AllQueries.Count)
        ]
        return tables + queries

    def _close(self) -> None:
        """Access を終了し、一時コピーを削除する。2回呼んでも安全。"""
        access = self._access
        self._access = None
        try:
            if access:
                access.Quit()
        finally:
            temporary_directory = self._temporary_directory
            self._temporary_directory = None
            if temporary_directory:
                temporary_directory.cleanup()

    def _ensure_source(self, source: str) -> None:
        names = self.table_names()
        if source not in names:
            raise AccessSourceNotFoundError(source, names)

    def _backup(self, backup_days: int) -> None:
        backup_folder = _backup_folder()
        if is_dry_run():
            dry_run_log(
                "Access ファイルをバックアップ: %s → %s（保持日数: %d日）",
                self._path,
                backup_folder,
                backup_days,
            )
            return

        backup_path = backup_folder / DateNameBuilder(
            self._path.stem, ext=self._path.suffix
        ).prefix(date_format=BACKUP_DATE_FORMAT)
        try:
            backup_folder.mkdir(parents=True, exist_ok=True)
            _remove_expired_backups(backup_folder, self._path, backup_days)
            backup_path = _reserve_backup_path(backup_folder, self._path)
        except OSError as e:
            raise AccessBackupError(self._path, backup_path, e) from e
        lock_path = self._path.with_suffix(".laccdb" if self._path.suffix == ".accdb" else ".ldb")
        if lock_path.exists():
            logger.warning(
                "他の利用者が Access を開いている状態でバックアップを取りました。"
                "コピーが不完全な可能性があります: %s",
                self._path,
            )
        try:
            shutil.copy2(self._path, backup_path)
        except Exception as e:
            try:
                backup_path.unlink()
            except OSError as cleanup_error:
                logger.debug(
                    "失敗したバックアップの残骸を削除できませんでした: %s（%s）",
                    backup_path,
                    cleanup_error,
                )
            raise AccessBackupError(self._path, backup_path, e) from e
        logger.info("Access ファイルをバックアップしました: %s", backup_path)


def _backup_folder() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "comken" / BACKUP_FOLDER_NAME
    return Path.home() / ".comken" / BACKUP_FOLDER_NAME


def _reserve_backup_path(folder: Path, source: Path) -> Path:
    filename = DateNameBuilder(source.stem, ext=source.suffix).prefix(
        date_format=BACKUP_DATE_FORMAT
    )
    sequence = 2
    candidate = folder / filename
    while True:
        try:
            candidate.open("xb").close()
            return candidate
        except FileExistsError:
            candidate = folder / f"{Path(filename).stem}_{sequence}{source.suffix}"
            sequence += 1


def _remove_expired_backups(folder: Path, source: Path, backup_days: int) -> None:
    cutoff = now() - timedelta(days=backup_days)
    filename_pattern = re.compile(
        rf"^\d{{8}}_\d{{6}}_{re.escape(source.stem)}(?:_\d+)?{re.escape(source.suffix)}$"
    )
    try:
        backup_paths = list(folder.iterdir())
    except OSError as e:
        logger.debug("バックアップフォルダを確認できませんでした: %s（%s）", folder, e)
        return
    for backup_path in backup_paths:
        if not filename_pattern.fullmatch(backup_path.name):
            continue
        try:
            modified = backup_path.stat().st_mtime
            if modified < cutoff.timestamp():
                backup_path.unlink()
        except OSError as e:
            logger.debug("期限切れバックアップを削除できませんでした: %s（%s）", backup_path, e)
