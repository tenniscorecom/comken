"""Microsoft Access のマクロ実行・データ出力。"""

from collections.abc import Iterator
from pathlib import Path

import win32com.client

from ..constants import Encoding
from ..exceptions import (
    AccessFileNotFoundError,
    AccessRoutineError,
    AccessSourceNotFoundError,
)
from ..runtime import dry_run_log, is_dry_run
from ..utils.files.base import FileBase

ACCESS_EXPORT_DELIMITED = 2
ACCESS_OPEN_TABLE = 0
ACCESS_OPEN_QUERY = 1
CP932_CODE_PAGE = 932
UTF8_CODE_PAGE = 65001
ROWS_BATCH_SIZE = 1000
_ENCODING_CODE_PAGES = {
    Encoding.CP932: CP932_CODE_PAGE,
    Encoding.UTF8_SIG: UTF8_CODE_PAGE,
}


class AccessDatabase(FileBase):
    """Access データベースを COM で操作する。

    数十万件を CSV に出す場合は、Python にデータを載せない ``export_csv()`` を使う。
    ``rows()`` は逐次処理用であり、結果を ``list`` にすると全件分のメモリを消費する。
    """

    SUFFIXES = (".accdb", ".mdb")

    def __init__(self, path: str | Path) -> None:
        super().__init__(path)
        if not self.path.is_file():
            raise AccessFileNotFoundError(self.path)
        # DispatchEx は利用者が手で開いている Access とは別のプロセスを起動する。
        self._access = win32com.client.DispatchEx("Access.Application")
        self._access.Visible = False
        try:
            self._access.OpenCurrentDatabase(str(self.path.resolve()))
        except Exception:
            self._access.Quit()
            raise

    def __enter__(self) -> "AccessDatabase":
        return self

    def __exit__(self, *args: object) -> None:
        self._close()

    def run_macro(self, name: str) -> None:
        """Access マクロを実行する。

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
        """Access を終了する。2回呼んでも安全。"""
        access = self._access
        self._access = None
        if access:
            access.Quit()

    def _ensure_source(self, source: str) -> None:
        names = self.table_names()
        if source not in names:
            raise AccessSourceNotFoundError(source, names)
