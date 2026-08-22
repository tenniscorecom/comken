"""comken/toolbox/excel/workbook.py — Excel ブックとデータ領域を操作する。"""

import hashlib
import shutil
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self, TypeAlias, cast
from zipfile import ZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from comken.core.files import atomic_write, copy_to_local_if_large
from comken.exceptions import (
    EmptyHeaderCellError,
    ExcelFileNotFoundError,
    ExcelMacroPreservationError,
    ExcelSaveValidationError,
    SheetAlreadyExistsError,
    SheetNotFoundError,
    UnsupportedFileSuffixError,
)
from comken.runtime import dry_run_log, is_dry_run
from comken.toolbox.excel.sheet import Sheet

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
        local_copy: bool | None = None,
    ) -> None:
        """ブックをOpenPyXLで開く。

        利用者がエンジンを選ぶ必要はない。通常操作はOpenPyXLを使い、未計算の
        数式値の読取りとVBA実行だけ、一時的にExcel COMへ昇格する。
        ``local_copy=None`` の既定ではUNCパスだけローカルコピーを使う。
        ``True`` で強制、``False`` で無効化でき、保存先は常に元ファイルになる。

        ``read_only``、dry-run、またはwithブロックが例外で終わった場合は保存しない。
        """
        self.path = Path(source)
        if self.path.suffix.casefold() not in _EXCEL_SUFFIXES:
            raise UnsupportedFileSuffixError(self.path, tuple(sorted(_EXCEL_SUFFIXES)))
        self._types = dict(types or {})
        self._read_only = read_only
        self._local_copy_path: Path | None = None
        self._working_copy_is_stale = False
        self._is_closed = False
        self._is_dirty = False
        should_copy = self._is_unc_path(source) if local_copy is None else local_copy
        if should_copy and self.path.exists():
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
                # openpyxlのReadOnlyWorksheetはExcelテーブル定義を公開しないため、
                # Table APIをread_onlyでも利用できるよう通常Worksheetで開く。
                read_only=False,
                keep_vba=self.path.suffix.casefold() in {".xlsm", ".xltm"},
            )
        else:
            if read_only:
                raise ExcelFileNotFoundError(self.path)
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
        return self.sheet(self._with_python_prefix(name))

    def create_data_sheet(self, name: str) -> "Sheet":
        """指定名の空のデータシートを作成する。"""
        self._ensure_writable("create_data_sheet")
        full_name = self._with_python_prefix(name)
        if full_name in self._workbook.sheetnames:
            raise SheetAlreadyExistsError(full_name)
        worksheet = self._workbook.create_sheet(full_name)
        self._mark_dirty()
        return Sheet(self, worksheet)

    def list_data_sheets(self) -> list[str]:
        """データシート名をブック内の順序で返す。"""
        self._ensure_open()
        return [name for name in self._workbook.sheetnames if self._is_data_sheet_name(name)]

    def _read_range_with_com(
        self, sheet_name: str, min_col: int, min_row: int, max_col: int, max_row: int
    ) -> list[tuple[Any, ...]]:
        """実テーブル範囲だけをCOMの計算値で読む。"""
        if self._is_dirty:
            self._prepare_com_working_copy()
        self._sync_working_file()
        from comken.toolbox.windows.handler import ExcelComHandler

        with ExcelComHandler(self._working_path, local_copy_threshold_mb=0) as excel_com:
            return excel_com.read_range(sheet_name, min_col, min_row, max_col, max_row)

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
        original_vba = self._vba_digest(self.path)
        with atomic_write(self.path) as temporary_path:
            self._workbook.save(temporary_path)
            verification = None
            try:
                verification = load_workbook(
                    temporary_path,
                    read_only=True,
                    keep_vba=self.path.suffix.casefold() in {".xlsm", ".xltm"},
                )
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as error:
                raise ExcelSaveValidationError(self.path, error) from error
            finally:
                if verification is not None:
                    verification.close()
            if original_vba is not None and self._vba_digest(temporary_path) != original_vba:
                raise ExcelMacroPreservationError(self.path)
        self._is_dirty = False
        # 明示 save() 後も with 内でCOM操作を続けられる。次のCOM利用時に
        # 保存後の原本からローカル作業コピーを同期し、古い値を開かない。
        self._working_copy_is_stale = self._working_path != self.path

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
        if self._working_copy_is_stale and self.path.exists():
            shutil.copy2(self.path, self._working_path)
            self._working_copy_is_stale = False
        working_file_is_empty = (
            not self._working_path.exists() or self._working_path.stat().st_size == 0
        )
        if self._is_dirty or working_file_is_empty:
            self._workbook.save(self._working_path)
            self._working_copy_is_stale = False

    def _prepare_com_working_copy(self) -> None:
        """マクロの変更を正常終了まで元ファイルから隔離する作業コピーを用意する。"""
        if self._local_copy_path is not None:
            return
        if self.path.exists():
            self._working_path, self._local_copy_path = copy_to_local_if_large(
                self.path, threshold_mb=_FORCED_LOCAL_COPY_THRESHOLD_MB
            )
            self._working_copy_is_stale = False
            return
        import tempfile

        suffix = self.path.suffix or ".xlsx"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
            self._working_path = Path(temp_file.name)
        self._local_copy_path = self._working_path
        self._working_copy_is_stale = False

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

    def _cached_range(
        self, sheet_name: str, min_col: int, min_row: int, max_col: int, max_row: int
    ) -> tuple[list[tuple[Any, ...]], bool]:
        """実テーブル範囲の保存済み計算値と、COM再計算の要否を返す。"""
        if self._working_copy_is_stale:
            self._sync_working_file()
        formula_sheet = self._workbook[sheet_name]
        if self._is_dirty or not self._working_path.exists():
            rows = [
                tuple(
                    formula_sheet.cell(row=row_number, column=column).value
                    for column in range(min_col, max_col + 1)
                )
                for row_number in range(min_row, max_row + 1)
            ]
            needs_com = any(
                isinstance(value, str) and value.startswith("=") for row in rows for value in row
            )
            return rows, needs_com
        cached_workbook = load_workbook(self._working_path, data_only=True, read_only=True)
        try:
            cached_sheet = cached_workbook[sheet_name]
            rows: list[tuple[Any, ...]] = []
            needs_com = False
            for row_number in range(min_row, max_row + 1):
                row = tuple(
                    cached_sheet.cell(row=row_number, column=column).value
                    for column in range(min_col, max_col + 1)
                )
                rows.append(row)
                for column, cached_value in zip(range(min_col, max_col + 1), row, strict=True):
                    formula = formula_sheet.cell(row=row_number, column=column).value
                    if (
                        isinstance(formula, str)
                        and formula.startswith("=")
                        and (cached_value is None or self._is_dirty)
                    ):
                        needs_com = True
            return rows, needs_com
        finally:
            cached_workbook.close()

    @staticmethod
    def _is_unc_path(path: str | Path) -> bool:
        """WindowsのUNC表記かを、ファイルの存在確認なしで判定する。"""
        return str(path).replace("/", "\\").startswith("\\\\")

    @staticmethod
    def _vba_digest(path: Path) -> bytes | None:
        """マクロ付き形式に含まれるVBAバイナリのハッシュを返す。"""
        if not path.exists() or path.suffix.casefold() not in {".xlsm", ".xltm"}:
            return None
        try:
            with ZipFile(path) as archive:
                return hashlib.sha256(archive.read("xl/vbaProject.bin")).digest()
        except KeyError:
            return None

    def _is_pristine_workbook(self) -> bool:
        worksheet = cast(Worksheet, self._workbook.active)
        return len(self._workbook.worksheets) == 1 and worksheet["A1"].value is None

    def _is_data_sheet_name(self, name: str) -> bool:
        return name.startswith(self.PY_PREFIX)

    def _with_python_prefix(self, name: str) -> str:
        """利用者が短い名前を書いたとき、Python管理用の名前を補う。"""
        if self._is_data_sheet_name(name):
            return name
        return f"{self.PY_PREFIX}{name}"
