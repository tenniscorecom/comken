"""comken/core/table/comparison.py — 2つのTableをキーで比較する。"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from comken.core.table.model import Table
from comken.exceptions.table import TableDuplicateKeyError, TransferMappingError

Row = dict[str, Any]


@dataclass(frozen=True)
class TableComparison:
    """readとwriteの比較結果を、方向が分かる名前で保持する。"""

    only_in_read: Table
    only_in_write: Table
    changed: Table
    same: Table


def compare_tables(
    read: Table,
    write: Table,
    *,
    read_key: str | Sequence[str],
    write_key: str | Sequence[str],
) -> TableComparison:
    """2つのTableをキーで比較し、4種類のTableに分けて返す。"""
    read_keys = [read_key] if isinstance(read_key, str) else list(read_key)
    write_keys = [write_key] if isinstance(write_key, str) else list(write_key)
    if len(read_keys) != len(write_keys):
        raise TransferMappingError
    read._check_columns(read_keys)
    write._check_columns(write_keys)
    read_value_columns = [column for column in read.columns if column not in read_keys]
    write_value_columns = [column for column in write.columns if column not in write_keys]
    # 辞書行は列順に依存しないため、同じ列名が揃っていれば比較できる。
    if set(read_value_columns) != set(write_value_columns):
        raise TransferMappingError
    generated_columns = {f"write_{column}" for column in write.columns}
    if generated_columns.intersection(read.columns):
        # changed の列名が既存列と衝突すると値を区別できないため、曖昧な結果を返さない。
        raise TransferMappingError
    read_index = _index_rows(read.read_rows(), read_keys)
    write_index = _index_rows(write.read_rows(), write_keys)
    read_only, write_only, changed, same = [], [], [], []
    for key, read_row in read_index.items():
        write_row = write_index.get(key)
        if write_row is None:
            read_only.append(read_row)
        elif _values_without_keys(read_row, read_keys) == _values_without_keys(
            write_row, write_keys
        ):
            same.append(read_row)
        else:
            changed.append(
                {
                    **read_row,
                    **{f"write_{column}": value for column, value in write_row.items()},
                }
            )
    for key, write_row in write_index.items():
        if key not in read_index:
            write_only.append(write_row)
    return TableComparison(
        Table(read.columns, read_only, types=read.types),
        Table(write.columns, write_only, types=write.types),
        Table(
            [*read.columns, *[f"write_{column}" for column in write.columns]],
            changed,
        ),
        Table(read.columns, same, types=read.types),
    )


def _key(row: Row, columns: Sequence[str]) -> tuple[Any, ...]:
    return tuple(row[column] for column in columns)


def _index_rows(rows: list[Row], columns: Sequence[str]) -> dict[tuple[Any, ...], Row]:
    index: dict[tuple[Any, ...], Row] = {}
    for row in rows:
        key = _key(row, columns)
        if key in index:
            raise TableDuplicateKeyError(list(columns), key)
        index[key] = row
    return index


def _values_without_keys(row: Row, keys: Sequence[str]) -> dict[str, Any]:
    return {column: value for column, value in row.items() if column not in keys}


__all__ = ["TableComparison", "compare_tables"]
