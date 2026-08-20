"""comken/toolbox/table.py — 既存のCSV・Excelクラス間で行を転記する。"""

import logging
from collections.abc import Callable, Mapping
from enum import Enum, auto
from typing import Final

from comken.core.timer import measure
from comken.exceptions.table import TransferMappingError
from comken.toolbox.csv import CsvReader, CsvWriter
from comken.toolbox.excel import Sheet

logger = logging.getLogger(__name__)

Row = dict[str, object]
Source = CsvReader | Sheet
Destination = CsvWriter | Sheet


class _TransferControl(Enum):
    STOP = auto()


Transform = Callable[[Row], Mapping[str, object] | None | _TransferControl]


class Transfer:
    """既存のCSV・Excelクラス間で、列マッピングに従って行を転記する。

    CSVの転記先は、転記先の列名と順序が一致するように
    ``CsvWriter(path, fieldnames=list(mapping.values()))`` と構築する。
    Excelを転記元または転記先にする場合は、``ExcelWriter.sheet()`` で取得した
    ``Sheet`` を渡す。Excelファイルの保存は呼び出し側で ``save()`` する。
    """

    STOP: Final = _TransferControl.STOP

    def __init__(
        self,
        source: Source,
        destination: Destination,
        mapping: Mapping[str, str],
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
        destination_rows: list[Row] = []
        read_count = 0
        for source_row in _read_source_rows(self._source):
            read_count += 1
            candidate: Mapping[str, object] | None | _TransferControl = source_row
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
        _write_destination_rows(
            self._destination,
            destination_rows,
            list(self._mapping.values()),
        )
        logger.debug("Transfer完了: 転記件数=%d", len(destination_rows))
        return len(destination_rows)


def _read_source_rows(source: Source) -> list[Row]:
    return [dict(row) for row in source.rows()]


def _write_destination_rows(
    destination: Destination,
    rows: list[Row],
    columns: list[str],
) -> None:
    if isinstance(destination, CsvWriter):
        destination.write_rows(rows)
        return
    destination.ws.delete_rows(1, destination.ws.max_row)
    if rows:
        destination.write_table(rows, headers=columns)
    else:
        destination.write_row(1, columns)


__all__ = ["Transfer"]
