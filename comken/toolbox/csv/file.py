"""comken/toolbox/csv/file.py — CSV ファイルを1つのデータ領域として扱う。"""

import csv
import re
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Self, TypeAlias

from comken.constants import Encoding
from comken.core.table.model import Table
from comken.exceptions.table import InvalidTableInputError

Value: TypeAlias = str | int | float | bool | datetime

_INTEGER_PATTERN = re.compile(r"^[+-]?\d+$")
_FLOAT_PATTERN = re.compile(r"^[+-]?(?:\d+\.\d*|\d*\.\d+)(?:[eE][+-]?\d+)?$")
_DATETIME_FORMATS = ("%Y/%m/%d", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S")


class CSV:
    """CSV ファイルをヘッダー付きのデータ領域として読み書きする。

    CsvReader/CsvWriter の個別操作をまとめ、ExcelTable と同じ「行の集合」として
    Transfer へ渡せる境界を提供する。
    """

    def __init__(
        self,
        source: str | Path,
        *,
        encoding: str = Encoding.UTF8_SIG,
        types=None,
        read_only: bool = False,
        dry_run: bool = False,
    ) -> None:
        self.path = Path(source)
        self._encoding = encoding
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
            and not (self._read_only or self._dry_run)
            and self._pending is not None
        ):
            self._write(self._pending)

    def read(self) -> Table:
        """全行を読み、指定された列だけを変換したTableを返す。"""
        if self._pending is not None:
            # replace/write の結果は保存前でも、同じ処理中の「現在の Table」として読める。
            return self._pending
        if not self.path.exists() or self.path.stat().st_size == 0:
            return Table([], [], types=self._types)
        with self.path.open("r", encoding=self._encoding, newline="") as file:
            reader = csv.DictReader(file)
            columns = [str(column) for column in reader.fieldnames or []]
            rows = [
                {str(key): value for key, value in row.items() if key is not None} for row in reader
            ]
            return Table(columns, rows, types=self._types)

    def replace(self, rows: list[dict[str, Value]] | Table) -> None:
        """ファイルのデータ領域を全置換する。"""
        if not isinstance(rows, (list, Table)):
            raise InvalidTableInputError("CSV の置換には Table または行リストを指定してください。")
        table = (
            rows
            if isinstance(rows, Table)
            else Table(list(rows[0]) if rows else [], rows, types=self._types)
        )
        self._pending = table
        # replace は計画を作るだけにする。途中で例外が起きたときに、
        # それまでの一部だけがファイルへ残ると復旧しにくいためである。

    def write(self, table: Table) -> None:
        """Tableを保存対象として受け取る。確定はsaveまたはwith正常終了で行う。"""
        self.replace(table)

    def save(self) -> None:
        # replace はメモリ上で準備し、save または正常終了した with でだけファイルへ反映する。
        if self._pending is not None and not self._read_only and not self._dry_run:
            self._write(self._pending)
            self._pending = None

    def _write(self, table: Table) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        rows = table.read()
        if not rows:
            self.path.write_text("", encoding=self._encoding)
            return
        headers = table.columns
        with self.path.open("w", encoding=self._encoding, newline="") as file:
            writer = csv.DictWriter(file, fieldnames=headers, extrasaction="raise")
            writer.writeheader()
            writer.writerows(rows)

    def count(self) -> int:
        """データ行数を返す。"""
        return len(self._pending) if self._pending is not None else len(self.read())


def _convert_value(value: str | None) -> Value:
    if value is None or value == "":
        return ""
    if _INTEGER_PATTERN.fullmatch(value):
        return int(value)
    if _FLOAT_PATTERN.fullmatch(value):
        return float(value)
    if value.casefold() in {"true", "false"}:
        return value.casefold() == "true"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass
    for date_format in _DATETIME_FORMATS:
        try:
            # 業務 CSV の日時はタイムゾーン情報を持たないローカル時刻として扱う。
            return datetime.strptime(value, date_format)  # noqa: DTZ007
        except ValueError:
            continue
    return value
