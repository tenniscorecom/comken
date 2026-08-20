"""comken/toolbox/table.py — CSV・Excelを同じ表データとして扱う入口。"""

import logging
from collections.abc import Callable, Iterable, Iterator, Mapping
from enum import Enum, auto
from pathlib import Path
from typing import Any, Final, Self

from comken.constants import Encoding
from comken.core.timer import measure
from comken.exceptions.table import TableNotOpenError, TransferMappingError
from comken.toolbox.csv import CsvReader, CsvWriter
from comken.toolbox.excel import ExcelWriter, Sheet

Row = dict[str, Any]


class _TransferControl(Enum):
    STOP = auto()


Transform = Callable[[Row], Mapping[str, object] | None | _TransferControl]

logger = logging.getLogger(__name__)


class CSV:
    """CSVを列名付きの行として読み書きする。"""

    def __init__(self, path: str | Path, encoding: str = Encoding.AUTO) -> None:
        self.path = Path(path)
        self._encoding = encoding

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def rows(self) -> Iterator[Row]:
        """各行を列名でアクセスできる辞書として返す。"""
        yield from CsvReader(self.path, encoding=self._encoding).rows()

    def write_rows(
        self, rows: Iterable[Mapping[str, object]], columns: Iterable[str] | None = None
    ) -> None:
        """行をCSVへ上書き保存する。列順は最初の行に合わせる。"""
        materialized = [dict(row) for row in rows]
        if not materialized and columns is None:
            return
        fieldnames = list(columns) if columns is not None else list(materialized[0])
        CsvWriter(self.path, fieldnames, encoding=self._encoding).write_rows(materialized)


class Excel:
    """Excelの1シートを列名付きの行として読み書きする。"""

    def __init__(self, path: str | Path, sheet: str = "Sheet1") -> None:
        self.path = Path(path)
        self._sheet_name = sheet
        self._book: ExcelWriter | None = None
        self._is_dirty = False

    def __enter__(self) -> Self:
        self._book = ExcelWriter(self.path) if self.path.exists() else ExcelWriter.create(self.path)
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._book is None:
            return
        if exc_type is None and self._is_dirty:
            self._book.save()
        self._book.close()

    def rows(self) -> Iterator[Row]:
        """各行を列名でアクセスできる辞書として返す。"""
        yield from self._require_book().rows(self._sheet_name)

    def write_rows(
        self, rows: Iterable[Mapping[str, object]], columns: Iterable[str] | None = None
    ) -> None:
        """選択中のシートへ列名と行を書き込む。"""
        materialized = [dict(row) for row in rows]
        if not materialized and columns is None:
            return
        sheet = self._require_book().sheet(self._sheet_name)
        sheet.ws.delete_rows(1, sheet.ws.max_row)
        if materialized:
            sheet.write_table(materialized)
        elif columns is not None:
            sheet.write_row(1, list(columns))
        self._is_dirty = True

    def sheet(self, name: str | None = None) -> Sheet:
        """セルや書式を操作するシートを返す。"""
        self._is_dirty = True
        return self._require_book().sheet(name or self._sheet_name)

    def _require_book(self) -> ExcelWriter:
        if self._book is None:
            raise TableNotOpenError("Excel")
        return self._book


class Transfer:
    """列マッピングに従って表データを一方向へ転記する。"""

    STOP: Final = _TransferControl.STOP

    def __init__(
        self, source: CSV | Excel, destination: CSV | Excel, mapping: Mapping[str, str]
    ) -> None:
        if not mapping:
            raise TransferMappingError
        self._source = source
        self._destination = destination
        self._mapping = dict(mapping)

    @measure
    def run(self, transform: Transform | None = None) -> int:
        """転記元を加工・選別して転記し、転記件数を返す。

        ``transform`` は転記元1件のコピーを受け取る。辞書を返すとその内容を転記し、
        ``None`` を返すとその件を除外し、``Transfer.STOP`` を返すと以降を処理しない。
        省略時は全件をそのまま転記する。
        """
        logger.debug(
            "Transfer開始: 転記元=%s 転記先=%s マッピング列数=%d",
            type(self._source).__name__,
            type(self._destination).__name__,
            len(self._mapping),
        )
        logger.debug("転記元データ取得開始")
        source_rows = self._source.rows()
        destination_rows: list[Row] = []
        read_count = 0
        for source_row in source_rows:
            read_count += 1
            candidate: Mapping[str, object] | None | _TransferControl = dict(source_row)
            if transform is not None:
                candidate = transform(dict(source_row))
            if candidate is self.STOP:
                logger.debug("転記元データ取得を停止: 取得件数=%d", read_count)
                break
            if candidate is None:
                continue
            destination_rows.append(
                {
                    destination: candidate.get(source)
                    for source, destination in self._mapping.items()
                }
            )
        logger.debug(
            "転記元データ取得完了: 取得件数=%d 転記対象件数=%d",
            read_count,
            len(destination_rows),
        )
        logger.debug("転記先書き込み開始: 件数=%d", len(destination_rows))
        self._destination.write_rows(destination_rows, self._mapping.values())
        logger.debug("Transfer完了: 転記件数=%d", len(destination_rows))
        return len(destination_rows)


__all__ = ["CSV", "Excel", "Transfer"]
