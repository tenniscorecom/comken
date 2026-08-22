"""メモリ上の Table 同士を転記する。"""

from collections.abc import Callable, Mapping, Sequence
from enum import Enum, auto
from typing import Any, Final

from comken.core.table.model import Table
from comken.exceptions.table import (
    InvalidTableInputError,
    TransferDestinationMultipleMatchError,
    TransferMappingError,
    TransferRowError,
)

Row = dict[str, Any]


class _Control(Enum):
    SKIP = auto()
    STOP = auto()


Transform = Callable[[Row, Row | None], None | _Control]


class Transfer:
    """Tableを入出力にして、キーで行を更新または追加する。

    保存は担当しない。呼び出し側が最後にCSVやExcelへTableを書き込むため、
    転記途中の例外でファイルが半端な状態になることを防げる。
    """

    SKIP: Final = _Control.SKIP
    STOP: Final = _Control.STOP

    def __init__(
        self,
        source: Table,
        destination: Table,
        mapping: Mapping[str, str] | None = None,
        *,
        read_key: str | Sequence[str] | None = None,
        write_key: str | Sequence[str] | None = None,
    ) -> None:
        if not isinstance(source, Table) or not isinstance(destination, Table):
            raise InvalidTableInputError("Transferの入出力にはTableを指定してください。")
        if read_key is None or write_key is None:
            raise TransferMappingError
        self.source, self.destination = source, destination
        self.mapping = dict(mapping or {})
        self.read_keys = [read_key] if isinstance(read_key, str) else list(read_key)
        self.write_keys = [write_key] if isinstance(write_key, str) else list(write_key)
        if len(self.read_keys) != len(self.write_keys):
            raise TransferMappingError

    def run(  # noqa: C901
        self,
        *,
        transform: Transform | None = None,
        mapping: Mapping[str, str] | None = None,
    ) -> Table:
        """転記し、更新後の転記先Tableを返す。"""
        transfer_mapping = dict(mapping or self.mapping)
        if not transfer_mapping:
            raise TransferMappingError
        self.source._check_columns([*self.read_keys, *transfer_mapping.keys()])
        self.destination._check_columns([*self.write_keys, *transfer_mapping.values()])
        # 複合キーも tuple にすると、キー列の組み合わせ単位で更新・追加を判断できる。
        index: dict[tuple[Any, ...], Row] = {}
        for row in self.destination:
            key = tuple(row[column] for column in self.write_keys)
            if key in index:
                raise TransferDestinationMultipleMatchError(",".join(self.write_keys), key)
            index[key] = row
        for source_row in self.source:
            key = tuple(source_row[column] for column in self.read_keys)
            destination_row = index.get(key)
            result = transform(source_row, destination_row) if transform else None
            if result is self.STOP:
                break
            if result is self.SKIP:
                continue
            if result is not None:
                raise TransferRowError(0, "transformはNone、SKIP、STOPのいずれかを返してください。")
            if destination_row is None:
                destination_row = dict.fromkeys(self.destination.columns, "")
                for source_key, destination_key in zip(
                    self.read_keys, self.write_keys, strict=True
                ):
                    destination_row[destination_key] = source_row[source_key]
                self.destination.append(destination_row)
                # Table.append は型変換した行を保持するので、その実体を以後更新する。
                destination_row = self.destination.rows[-1]
                index[key] = destination_row
            for source_column, destination_column in transfer_mapping.items():
                destination_row[destination_column] = source_row[source_column]
        return self.destination


__all__ = ["Transfer"]
