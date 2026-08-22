"""comken/toolbox/excel/workbook.py — Excel ブックとデータ領域を操作する。"""

from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self, TypeAlias, cast

from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from comken.core.files import copy_to_local_if_large
from comken.exceptions import (
    EmptyHeaderCellError,
    SheetAlreadyExistsError,
    SheetNotFoundError,
)
from comken.runtime import dry_run_log, is_dry_run
from comken.toolbox.excel.sheet import Sheet
from comken.toolbox.table_model import Table

Value: TypeAlias = str | int | float | bool | datetime
_EXCEL_SUFFIXES = {".xlsx", ".xlsm", ".xltx", ".xltm"}
_FORCED_LOCAL_COPY_THRESHOLD_MB = 0.000001


class Excel:
    """Excel ワークブックを開き、シート単位の操作を提供する。"""

    PY_PREFIX = "PY_"

    def __init__(
        self,
        source: str | Path,
        *,
        types: Mapping[str, Callable[[Any], Any]] | None = None,
        read_only: bool = False,
        local_copy: bool = False,
    ) -> None:
        """ブックをOpenPyXLで開く。

        利用者がエンジンを選ぶ必要はない。通常操作はOpenPyXLを使い、未計算の
        数式値の読取りとVBA実行だけ、一時的にExcel COMへ昇格する。
        ``local_copy=True`` でも正常終了時の保存先は元ファイルになる。

        ``read_only``、dry-run、またはwithブロックが例外で終わった場合は保存しない。
        """
        self.path = Path(source)
        self._types = dict(types or {})
        self._read_only = read_only
        self._local_copy_path: Path | None = None
        self._is_closed = False
        self._is_dirty = False
        if local_copy and self.path.exists():
            # ネットワーク上のブックを直接扱うと OpenPyXL/Excel の I/O が不安定に
            # なることがある。作業中だけローカルを使い、保存時に元のパスへ戻す。
            self._working_path, self._local_copy_path = copy_to_local_if_large(
                self.path, threshold_mb=_FORCED_LOCAL_COPY_THRESHOLD_MB
            )
        else:
            self._working_path = self.path
        if self._working_path.exists():
            self._workbook = load_workbook(
                self._working_path,
                read_only=read_only,
                keep_vba=self.path.suffix.casefold() in {".xlsm", ".xltm"},
            )
        else:
            if read_only:
                raise FileNotFoundError(self.path)
            self._workbook = Workbook()

    def __enter__(self) -> Self:
        self._ensure_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        # 例外時に保存すると、途中までの変更で元ファイルを壊す可能性がある。
        # read_only と dry-run の扱いは close() 側へ集約している。
        self.close(save=exc_type is None)

    def sheet(self, name: str | None = None) -> "Sheet":
        """名前でシートを取得する。未存在の新規ブックでは最初のシートを改名する。"""
        self._ensure_open()
        if name is None:
            display_sheets = [
                sheet for sheet in self._workbook.sheetnames if not self._is_data_sheet_name(sheet)
            ]
            if len(display_sheets) != 1:
                raise SheetNotFoundError("省略", display_sheets)
            name = display_sheets[0]
        if name not in self._workbook.sheetnames:
            if not self.path.exists() and self._is_pristine_workbook():
                cast(Worksheet, self._workbook.active).title = name
                self._is_dirty = True
            else:
                raise SheetNotFoundError(name, self._workbook.sheetnames)
        return Sheet(self, self._workbook[name])

    def data_sheet(self, name: str | None = None) -> "Sheet":
        """データシートを取得する。名前を省略できるのは1枚のときだけ。"""
        self._ensure_open()
        names = self.list_data_sheets()
        if name is None:
            if len(names) != 1:
                raise SheetNotFoundError("データシート省略", names)
            name = names[0]
        return self.sheet(self._with_data_prefix(name))

    def create_data_sheet(self, name: str) -> "Sheet":
        """指定名の空のデータシートを作成する。"""
        self._ensure_writable("create_data_sheet")
        full_name = self._with_data_prefix(name)
        if full_name in self._workbook.sheetnames:
            raise SheetAlreadyExistsError(full_name)
        worksheet = self._workbook.create_sheet(full_name)
        self._mark_dirty()
        return Sheet(self, worksheet)

    def list_data_sheets(self) -> list[str]:
        """データシート名をブック内の順序で返す。"""
        self._ensure_open()
        return [name for name in self._workbook.sheetnames if self._is_data_sheet_name(name)]

    def read_with_com(self, sheet_name: str | None = None):
        """Excel COMで計算結果を読み、Tableとして返す。"""
        if sheet_name is None:
            sheet_name = self.data_sheet()._worksheet.title
        else:
            sheet_name = self._with_data_prefix(sheet_name)
        rows = self.read_computed_rows_as_dicts(sheet_name, 1)
        columns = [str(column) for column in rows[0]] if rows else []
        normalized_rows = [
            {
                str(column): value
                if str(column) in self._types or value is None
                else str(value)
                for column, value in row.items()
            }
            for row in (rows[1:] if rows else [])
        ]
        return Table(columns, normalized_rows, types=self._types)

    def close(self, *, save: bool = True) -> None:
        """ブックを閉じる。通常はwithの正常終了時に変更を自動保存する。"""
        if self._is_closed:
            return
        try:
            if save and self._is_dirty:
                self.save()
        finally:
            self._workbook.close()
            self._is_closed = True
            if self._local_copy_path is not None:
                self._local_copy_path.unlink(missing_ok=True)

    def save(self) -> None:
        """変更を元ファイルへ保存する。

        既存コードのために残しているが、通常はwithの正常終了時に自動保存される。
        read-onlyとdry-runではファイルを変更しない。
        """
        self._ensure_open()
        if self._read_only or not self._is_dirty:
            return
        if is_dry_run():
            dry_run_log("Excel を保存: %s", self.path)
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._workbook.save(self.path)
        self._is_dirty = False

    def run_macro(self, macro_name: str) -> None:
        """Excel COMへ一時的に昇格してVBAマクロを実行する。

        COMには元ファイルではなく作業ファイルを渡す。ローカルコピー利用時にも、
        例外終了なら元ファイルを変更しないというwithの契約を守るためである。
        """
        self._ensure_writable("run_macro")
        if is_dry_run():
            dry_run_log("Excel マクロを実行: %s (%s)", macro_name, self.path)
            return
        self._prepare_com_working_copy()
        self._sync_working_file()
        from comken.toolbox.windows.handler import ExcelComHandler

        with ExcelComHandler(self._working_path, local_copy_threshold_mb=0) as excel_com:
            excel_com.run_macro(macro_name)
            excel_com.save()
        self._reload_workbook()
        self._is_dirty = True

    def read_computed_rows(self, sheet_name: str, min_row: int = 2) -> list[tuple[Any, ...]]:
        """数式の計算結果を行単位で読む。未計算の数式がある場合だけCOMへ昇格する。"""
        rows, needs_com = self._cached_rows(sheet_name, min_row)
        if not needs_com:
            return rows
        # 書込み後の計算読取りでも、後続処理が例外なら元ファイルを変えない。
        # COMへ同期する先を一時コピーへ切り替えてから保存する。
        if self._is_dirty:
            self._prepare_com_working_copy()
        self._sync_working_file()
        from comken.toolbox.windows.handler import ExcelComHandler

        with ExcelComHandler(self._working_path, local_copy_threshold_mb=0) as excel_com:
            return excel_com.read_rows(sheet_name, min_row)

    def read_computed_rows_as_dicts(
        self, sheet_name: str, header_row: int = 1
    ) -> list[dict[str, Any]]:
        """見出し行をキーに計算結果を読む。未計算時だけCOMへ昇格する。"""
        rows = self.read_computed_rows(sheet_name, header_row)
        if not rows:
            return []
        headers = rows[0]
        empty_columns = [index for index, header in enumerate(headers, start=1) if header is None]
        if empty_columns:
            raise EmptyHeaderCellError(empty_columns)
        return [dict(zip(headers, row, strict=False)) for row in rows[1:]]

    def _ensure_open(self) -> None:
        if self._is_closed:
            raise RuntimeError("Excel はすでに閉じています。with ブロック内で操作してください。")

    def _mark_dirty(self) -> None:
        self._ensure_writable("書き込み")
        self._is_dirty = True

    def _ensure_writable(self, operation: str) -> None:
        self._ensure_open()
        if self._read_only:
            raise RuntimeError(f"read_only=True のExcelでは{operation}できません。")

    def _sync_working_file(self) -> None:
        """COMへ渡す前に現在状態を作業ファイルへ同期する。"""
        if self._is_dirty:
            self._workbook.save(self._working_path)

    def _prepare_com_working_copy(self) -> None:
        """マクロの変更を正常終了まで元ファイルから隔離する作業コピーを用意する。"""
        if self._local_copy_path is not None:
            return
        if self.path.exists():
            self._working_path, self._local_copy_path = copy_to_local_if_large(
                self.path, threshold_mb=_FORCED_LOCAL_COPY_THRESHOLD_MB
            )
            return
        self._working_path = self.path

    def _reload_workbook(self) -> None:
        self._workbook.close()
        self._workbook = load_workbook(
            self._working_path,
            keep_vba=self.path.suffix.casefold() in {".xlsm", ".xltm"},
        )

    def _cached_rows(self, sheet_name: str, min_row: int) -> tuple[list[tuple[Any, ...]], bool]:
        """キャッシュ値と数式を並べ、値がない数式だけをCOM昇格対象にする。"""
        cached_workbook = load_workbook(self._working_path, data_only=True, read_only=True)
        try:
            formula_sheet = self._workbook[sheet_name]
            cached_sheet = cached_workbook[sheet_name]
            max_column = formula_sheet.max_column
            rows: list[tuple[Any, ...]] = []
            needs_com = False
            for row_number in range(min_row, formula_sheet.max_row + 1):
                cached_row = tuple(
                    cached_sheet.cell(row=row_number, column=column).value
                    for column in range(1, max_column + 1)
                )
                rows.append(cached_row)
                for column, cached_value in enumerate(cached_row, start=1):
                    formula = formula_sheet.cell(row=row_number, column=column).value
                    is_uncalculated_formula = (
                        isinstance(formula, str)
                        and formula.startswith("=")
                        # OpenPyXLで何かを書いた後は、既存キャッシュが残っていても
                        # 現在の値に対応する保証がないのでExcelで再計算する。
                        and (cached_value is None or self._is_dirty)
                    )
                    if is_uncalculated_formula:
                        needs_com = True
            return rows, needs_com
        finally:
            cached_workbook.close()

    def _is_pristine_workbook(self) -> bool:
        worksheet = cast(Worksheet, self._workbook.active)
        return len(self._workbook.worksheets) == 1 and worksheet["A1"].value is None

    def _is_data_sheet_name(self, name: str) -> bool:
        return name.startswith(self.PY_PREFIX)

    def _with_data_prefix(self, name: str) -> str:
        """利用者が短い名前を書いたとき、Python管理用の名前を補う。"""
        if self._is_data_sheet_name(name):
            return name
        return f"{self.PY_PREFIX}{name}"
