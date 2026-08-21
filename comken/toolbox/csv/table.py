"""comken/toolbox/csv/table.py — CSV ファイルを1つのデータ領域として扱う。"""

import csv
import re
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Self, TypeAlias

from comken.constants import Encoding

Value: TypeAlias = str | int | float | bool | datetime

_INTEGER_PATTERN = re.compile(r"^[+-]?\d+$")
_FLOAT_PATTERN = re.compile(r"^[+-]?(?:\d+\.\d*|\d*\.\d+)(?:[eE][+-]?\d+)?$")
_DATETIME_FORMATS = ("%Y/%m/%d", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S")


class CSV:
    """CSV ファイルをヘッダー付きのデータ領域として読み書きする。"""

    def __init__(self, source: str | Path, *, encoding: str = Encoding.UTF8_SIG) -> None:
        self.path = Path(source)
        self._encoding = encoding

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def read(self) -> list[dict[str, Value]]:
        """全行を読み、推測した型の値を持つ辞書で返す。"""
        if not self.path.exists() or self.path.stat().st_size == 0:
            return []
        with self.path.open("r", encoding=self._encoding, newline="") as file:
            reader = csv.DictReader(file)
            return [
                {str(key): _convert_value(value) for key, value in row.items() if key is not None}
                for row in reader
            ]

    def replace(self, rows: list[dict[str, Value]]) -> None:
        """ファイルのデータ領域を全置換する。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not rows:
            self.path.write_text("", encoding=self._encoding)
            return
        headers = list(rows[0])
        with self.path.open("w", encoding=self._encoding, newline="") as file:
            writer = csv.DictWriter(file, fieldnames=headers, extrasaction="raise")
            writer.writeheader()
            writer.writerows(rows)

    def count(self) -> int:
        """データ行数を返す。"""
        return len(self.read())


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
