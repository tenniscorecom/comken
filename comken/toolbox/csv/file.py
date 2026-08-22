"""comken/toolbox/csv/file.py — CSV ファイルを1つのデータ領域として扱う。"""

import csv
import io
from collections.abc import Callable, Mapping
from pathlib import Path
from types import TracebackType
from typing import Any, Self, TypeAlias

from comken.constants import Encoding
from comken.core.files import atomic_write
from comken.core.table.model import Table
from comken.exceptions.csv import (
    CsvColumnsRequiredError,
    CsvFileNotFoundError,
    CsvHeaderMissingError,
    CsvInvalidHeaderError,
    CsvRowLengthError,
    EncodingDetectionError,
)
from comken.exceptions.file import UnsupportedFileSuffixError
from comken.exceptions.table import InvalidTableInputError, InvalidTableOperationError
from comken.runtime import is_dry_run

Value: TypeAlias = str | int | float | bool


class CSV:
    """CSV ファイルを1つのデータ領域として読み書きする。

    Table と同じ「行の集合」として Transfer へ渡せる境界を提供する。
    ヘッダーのないファイルは ``columns`` で列名を指定する。
    """

    def __init__(
        self,
        source: str | Path,
        *,
        encoding: str = Encoding.AUTO,
        columns: list[str] | None = None,
        types: Mapping[str, Callable[[Any], Any]] | None = None,
        read_only: bool = False,
        dry_run: bool = False,
    ) -> None:
        self.path = Path(source)
        if self.path.suffix.lower() != ".csv":
            raise UnsupportedFileSuffixError(self.path, (".csv",))
        self._encoding = encoding
        self._columns = list(columns) if columns is not None else None
        self._types = dict(types or {})
        self._read_only = read_only
        self._dry_run = dry_run
        self._pending: Table | None = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if (
            exc_type is None
            and not (self._read_only or self._dry_run or is_dry_run())
            and self._pending is not None
        ):
            self._write(self._pending)

    def read(self) -> Table:
        """全行を読み、指定された列だけを変換したTableを返す。"""
        if self._pending is not None:
            # replace/write の結果は保存前でも、同じ処理中の「現在の Table」として読める。
            return self._pending
        if not self.path.exists():
            raise CsvFileNotFoundError(self.path)
        if self.path.stat().st_size == 0:
            if self._columns is None:
                raise CsvHeaderMissingError(self.path)
            return Table(self._columns, [], types=self._types)
        raw_rows = list(csv.reader(io.StringIO(self._read_text())))
        if not raw_rows and self._columns is None:
            # UTF-8 BOM は文字ではなく署名なので、BOM だけのファイルにも見出しはない。
            raise CsvHeaderMissingError(self.path)
        columns = self._columns if self._columns is not None else raw_rows.pop(0)
        self._validate_columns(columns)
        first_data_line = 1 if self._columns is not None else 2
        rows: list[dict[str, str]] = []
        for line_number, values in enumerate(raw_rows, start=first_data_line):
            if len(values) != len(columns):
                raise CsvRowLengthError(self.path, line_number, len(columns), len(values))
            rows.append(dict(zip(columns, values, strict=True)))
        return Table(columns, rows, types=self._types)

    def _validate_columns(self, columns: list[str]) -> None:
        if not columns:
            raise CsvHeaderMissingError(self.path)
        empty = [index for index, column in enumerate(columns, 1) if column == ""]
        if empty:
            raise CsvInvalidHeaderError(self.path, f"空の見出しがあります（{empty}列目）。")
        duplicates = [column for column in dict.fromkeys(columns) if columns.count(column) > 1]
        if duplicates:
            raise CsvInvalidHeaderError(self.path, f"重複する見出しがあります: {duplicates}")

    def _read_text(self) -> str:
        raw = self.path.read_bytes()
        if self._encoding != Encoding.AUTO:
            return raw.decode(self._encoding)
        for encoding in (Encoding.UTF8_SIG, Encoding.CP932):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise EncodingDetectionError(self.path)

    def replace(self, rows: list[dict[str, Value]] | Table) -> None:
        """ファイルのデータ領域を全置換する。"""
        if self._read_only:
            raise InvalidTableOperationError("read_only=True のCSVには書き込めません。")
        if not isinstance(rows, (list, Table)):
            raise InvalidTableInputError("CSV の置換には Table または行リストを指定してください。")
        if isinstance(rows, Table):
            table = rows
        elif rows:
            columns = self._columns or list(rows[0])
            table = Table(columns, rows, types=self._types)
        else:
            columns = self._columns
            if columns is None and self._pending is not None:
                columns = self._pending.columns
            if columns is None and self.path.exists() and self.path.stat().st_size > 0:
                columns = self.read().columns
            if columns is None:
                raise CsvColumnsRequiredError(self.path)
            table = Table(columns, [], types=self._types)
        self._pending = table
        # replace は計画を作るだけにする。途中で例外が起きたときに、
        # それまでの一部だけがファイルへ残ると復旧しにくいためである。

    def write(self, table: Table) -> None:
        """Tableを保存対象として受け取る。確定はsaveまたはwith正常終了で行う。"""
        self.replace(table)

    def append(self, rows: list[dict[str, Value]] | dict[str, Value] | Table) -> None:
        """行を保留中のTableへ追加する。確定はsaveまたはwith正常終了で行う。"""
        if self._read_only:
            raise InvalidTableOperationError("read_only=True のCSVには書き込めません。")
        if self._pending is not None or self.path.exists():
            current = self.read()
        elif self._columns is not None:
            current = Table(self._columns, [], types=self._types)
        else:
            raise CsvFileNotFoundError(self.path)
        if isinstance(rows, Table):
            additions = rows.read()
        elif isinstance(rows, dict):
            additions = [rows]
        elif isinstance(rows, list):
            additions = rows
        else:
            raise InvalidTableInputError(
                "CSV の追記には Table、1行、または行リストを指定してください。"
            )
        current.append(additions)
        self._pending = current

    def save(self) -> None:
        """保留中のTableをCSVファイルへ保存する。"""
        # replace はメモリ上で準備し、save または正常終了した with でだけファイルへ反映する。
        if (
            self._pending is not None
            and not self._read_only
            and not self._dry_run
            and not is_dry_run()
        ):
            self._write(self._pending)
            self._pending = None

    def _write(self, table: Table) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with (
            atomic_write(self.path) as temporary_path,
            temporary_path.open("w", encoding=self._write_encoding, newline="") as file,
        ):
            if not table.columns:
                return
            writer = csv.DictWriter(file, fieldnames=table.columns, extrasaction="raise")
            writer.writeheader()
            writer.writerows(table.read())

    @property
    def _write_encoding(self) -> str:
        return Encoding.UTF8_SIG if self._encoding == Encoding.AUTO else self._encoding

    def count(self) -> int:
        """データ行数を返す。"""
        return len(self._pending) if self._pending is not None else len(self.read())
