"""comken/toolbox/access/handler.py — Microsoft Access のマクロ実行・データ出力。"""

# AccessDatabase のメソッド注釈がクラス定義後の名前を参照するため、遅延評価する。
from __future__ import annotations

import logging
import re
import shutil
import tempfile
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any, Self

import win32com.client

from comken.constants import Encoding
from comken.core.clock import now
from comken.core.files import DateNameBuilder
from comken.core.files.base import FileBase
from comken.core.table import Table
from comken.core.timer import measure
from comken.exceptions import (
    AccessBackupError,
    AccessFileNotFoundError,
    AccessLocalCopyError,
    AccessRoutineError,
    AccessSourceNotFoundError,
)
from comken.runtime import dry_run_log, is_dry_run

logger = logging.getLogger(__name__)

ACCESS_EXPORT_DELIMITED = 2
ACCESS_OPEN_TABLE = 0
ACCESS_OPEN_QUERY = 1
DAO_FAIL_ON_ERROR = 128
CP932_CODE_PAGE = 932
UTF8_CODE_PAGE = 65001
ROWS_BATCH_SIZE = 1000
DEFAULT_BACKUP_DAYS = 7
BACKUP_DATE_FORMAT = "%Y%m%d_%H%M%S"
BACKUP_FOLDER_NAME = "backup"
# read_table() は全件を list にして返すため、この件数を超えるとメモリに厳しい。
# 大量データは read_rows() か export_csv() を使うよう、利用者へ知らせる境界。
_LARGE_TABLE_WARNING_THRESHOLD = 50_000
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
    バックアップ先は既定で元データベースと同じフォルダの ``backup``。
    数百 MB 以上のデータベースでは、ネットワーク越しのコピーに時間がかかる。
    ``backup_dir`` にローカルフォルダを指定すれば速くなるが、顧客情報がローカルに
    残ることを理解したうえで指定する。元データベースと同じ場所に控えを置くため、
    サーバー障害や誤削除では一緒に失われる。本格的な世代保全はサーバー側の
    バックアップに依存する。OneDrive などの同期フォルダでは控えも同期され、
    容量と帯域を消費する。

    数十万件を CSV に出す場合は、Python にデータを載せない ``export_csv()`` を使う。
    ``read_rows()`` は逐次処理用であり、結果を ``list`` にすると全件分のメモリを消費する。
    """

    SUFFIXES = (".accdb", ".mdb")

    def __init__(
        self,
        path: str | Path,
        local_copy: bool = True,
        backup: bool | None = None,
        backup_days: int = DEFAULT_BACKUP_DAYS,
        backup_dir: str | Path | None = None,
    ) -> None:
        super().__init__(path)
        if not self.path.is_file():
            raise AccessFileNotFoundError(self.path)
        if backup_days < 0:
            raise ValueError("backup_days は0以上で指定してください。")

        self._working_path = self._path
        self._backup_dir = (
            self._path.parent / BACKUP_FOLDER_NAME if backup_dir is None else Path(backup_dir)
        )
        self._temporary_directory: tempfile.TemporaryDirectory[str] | None = None
        # COM オブジェクトは型を持たず、閉じたあとは None になる。
        # 注釈が無いと型チェッカーが None 側だけを見て「DoCmd は無い」と言う
        self._access: Any = None
        should_backup = not local_copy if backup is None else backup

        if should_backup:
            self._backup(backup_days)
        elif not is_dry_run() and self._backup_dir.is_dir():
            _remove_expired_backups(self._backup_dir, self._path, backup_days)

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

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self._close()

    @measure
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

    @measure
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

    @measure
    def run_query(self, name: str) -> None:
        """保存済みのアクションクエリを名前で実行する。

        UPDATE・INSERT・DELETE・テーブル作成など、データを変更するクエリ向け。
        元データベースへ変更を反映する場合は、初期化時に ``local_copy=False`` を指定する。
        SELECT クエリの結果を読む場合は ``read_rows()``、CSVへ出す場合は ``export_csv()`` を使う。
        """
        self._ensure_query(name)
        if is_dry_run():
            dry_run_log("Access クエリを実行: %s（%s）", name, self.path)
            return
        try:
            # DAO_FAIL_ON_ERROR により、一部の行だけ更新して処理を続ける事故を防ぐ。
            self._access.CurrentDb().QueryDefs(name).Execute(DAO_FAIL_ON_ERROR)
        except Exception as e:
            raise AccessRoutineError(name, "クエリ", e) from e

    @measure
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

    def read_rows(self, source: str) -> Iterator[dict[str, object]]:
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

    def read_table(self, source: str) -> Table:
        """テーブルまたはクエリをメモリ上の ``Table`` として返す。

        全行をメモリへ載せるため、大量データには ``read_rows()`` を使う。
        ``_LARGE_TABLE_WARNING_THRESHOLD`` を超える行を読んだときは警告ログを出す。
        表として絞り込み・索引・転記を行う場合の明示的な入口。

        列名は ``read_rows()`` のイテレータから直接取れない（イテレータは
        行ごとにしか値を返さない）ため、レコードセットを別途開いて列名だけ
        先に取得する。0 件のときは ``read_rows()`` が空ジェネレータを返すので
        ``columns`` が空になるが、Access 側にもスキーマ API が無いため
        「0 件のとき列名が空」なのは仕様として許容する。
        """
        # 列名はレコードセットを開いた最初の1回で取れるので、先に取る
        self._ensure_source(source)
        recordset = self._access.CurrentDb().OpenRecordset(source)
        try:
            field_names = [
                str(recordset.Fields.Item(index).Name) for index in range(recordset.Fields.Count)
            ]
        finally:
            recordset.Close()
        rows = list(self.read_rows(source))
        if len(rows) > _LARGE_TABLE_WARNING_THRESHOLD:
            logger.warning(
                "AccessDatabase.read_table(%r) は %d 行を読み込みました。"
                "大量データは read_rows() でストリーミング読み込みする方がメモリに優しいです。",
                source,
                len(rows),
            )
        return Table(field_names, rows)

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

    def _ensure_query(self, name: str) -> None:
        query_names = [
            str(self._access.CurrentData.AllQueries.Item(index).Name)
            for index in range(self._access.CurrentData.AllQueries.Count)
        ]
        if name not in query_names:
            raise AccessSourceNotFoundError(name, query_names)

    def _backup(self, backup_days: int) -> None:
        backup_folder = self._backup_dir
        if is_dry_run():
            dry_run_log(
                "Access ファイルをバックアップ: %s → %s（保持日数: %d日）",
                self._path,
                backup_folder,
                backup_days,
            )
            return

        backup_path = backup_folder / DateNameBuilder(self._path.name).prefix(
            f"{{:{BACKUP_DATE_FORMAT}}}_"
        )
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
        logger.info("バックアップを作りました: %s", backup_path)


def _reserve_backup_path(folder: Path, source: Path) -> Path:
    filename = DateNameBuilder(source.name).prefix(f"{{:{BACKUP_DATE_FORMAT}}}_")
    sequence = 2
    candidate = folder / filename
    while True:
        try:
            # "xb" は既存ファイルがあると失敗する。空ファイルを作って名前を先に押さえる。
            with candidate.open("xb"):
                pass
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
    removed_count = 0
    for backup_path in backup_paths:
        if not filename_pattern.fullmatch(backup_path.name):
            continue
        try:
            modified = backup_path.stat().st_mtime
            if modified < cutoff.timestamp():
                backup_path.unlink()
                removed_count += 1
        except OSError as e:
            logger.debug("期限切れバックアップを削除できませんでした: %s（%s）", backup_path, e)
    if removed_count:
        logger.info(
            "バックアップを%d日分残す設定に従い、期限切れの控えを%d件削除しました。",
            backup_days,
            removed_count,
        )
