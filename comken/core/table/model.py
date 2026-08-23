"""comken/core/table/model.py — 保存先を持たない、初学者向けの表データモデル。

Table はメモリ上の行だけを担当します。CSV や Excel の保存処理をここへ
入れないことで、加工処理とファイル I/O の責任を分けています。
"""

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from comken.exceptions.table import (
    TableColumnNotFoundError,
    TableDuplicateKeyError,
    TableError,
    TableMergeColumnCollisionError,
    TableMergeSuffixError,
    TableRowColumnsError,
    TableTypeConversionError,
)


class Table:
    """列と辞書行をメモリで扱う表。

    CSVやExcelに直接依存しないため、加工処理をファイルI/Oから分離できます。
    ``types`` は入力時に明示された列だけを変換し、暗黙の型推測は行いません。
    """

    def __init__(
        self,
        columns: list[str] | tuple[str, ...],
        rows: list[dict[str, Any]],
        *,
        types: Mapping[str, Callable[[Any], Any]] | None = None,
    ) -> None:
        self.columns = list(columns)
        if len(self.columns) != len(set(self.columns)):
            raise TableError("列名は重複させられません。")
        self.types = dict(types or {})
        self._rows: list[dict[str, Any]] = [
            self._normalize(row, row_number) for row_number, row in enumerate(rows, 1)
        ]

    def _normalize(self, row: Mapping[str, Any], row_number: int) -> dict[str, Any]:
        missing = [column for column in self.columns if column not in row]
        extra = [column for column in row if column not in self.columns]
        if missing or extra:
            raise TableRowColumnsError(row_number, missing, extra)
        normalized = dict(row)
        for column, converter in self.types.items():
            if column not in self.columns:
                continue
            try:
                normalized[column] = converter(row[column])
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as exc:
                raise TableTypeConversionError(row_number, column, row[column]) from exc
        return normalized

    @property
    def rows(self) -> list[dict[str, Any]]:
        """行のコピーを返す（読み取り専用）。"""
        return [dict(row) for row in self._rows]

    def read(self) -> list[dict[str, Any]]:
        """現在の行をコピーして返す。元のTableは変更しない。"""
        return [dict(row) for row in self._rows]

    def __iter__(self):
        """各行のコピーを返す。反復中の変更は元のTableへ反映しない。"""
        return iter(self.read())

    def __len__(self) -> int:
        return len(self._rows)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, list):
            return self.read() == other
        return super().__eq__(other)

    def replace(self, rows: list[dict]) -> "Table":
        """表の全行を置き換え、同じTableを返す。"""
        self._rows = [self._normalize(row, row_number) for row_number, row in enumerate(rows, 1)]
        return self

    def append(self, rows: list[dict] | dict) -> "Table":
        """1行または複数行を末尾へ追加する。"""
        values = [rows] if isinstance(rows, dict) else rows
        start = len(self._rows) + 1
        normalized = [self._normalize(row, start + index) for index, row in enumerate(values)]
        self._rows.extend(normalized)
        return self

    def count(self) -> int:
        """行数を返す。"""
        return len(self._rows)

    def select(self, *columns: str) -> "Table":
        """指定した列だけを持つ新しいTableを返す。"""
        self._check_columns(columns)
        return Table(
            list(columns), [{column: row[column] for column in columns} for row in self._rows]
        )

    def filter(self, predicate: Callable[[dict], bool]) -> "Table":
        """条件に一致する行だけを持つ新しいTableを返す。"""
        # predicate は利用者コードなので、誤って行を書き換えても元の Table へ影響させない。
        rows = [dict(row) for row in self._rows if predicate(dict(row))]
        return Table(self.columns, rows, types=self.types)

    def column(self, name: str) -> list[Any]:
        """指定列の値を順番どおりに返す。"""
        self._check_columns([name])
        return [row[name] for row in self._rows]

    def index(self, key: str) -> dict[Any, dict]:
        """指定列をキーにした辞書を返す。"""
        self._check_columns([key])
        result: dict[Any, dict] = {}
        for row in self._rows:
            value = row[key]
            if value in result:
                raise TableDuplicateKeyError([key], value)
            result[value] = dict(row)
        return result

    def group_by(self, key: str) -> dict[Any, "Table"]:
        """指定列の値ごとにTableを分けて返す。"""
        self._check_columns([key])
        grouped: dict[Any, list[dict]] = {}
        for row in self._rows:
            grouped.setdefault(row[key], []).append(row)
        return {
            value: Table(self.columns, rows, types=self.types) for value, rows in grouped.items()
        }

    def merge(
        self,
        other: "Table",
        *,
        on: str,
        how: str = "left",
        suffixes: tuple[str, str] = ("_read", "_write"),
    ) -> "Table":
        """キー列で別のTableを結合し、新しいTableを返す。"""
        if how not in {"left", "inner"}:
            raise TableError("merge は left または inner のみ対応します。")
        self._check_columns([on])
        other._check_columns([on])
        if (
            not isinstance(suffixes, tuple)
            or len(suffixes) != 2
            or not all(isinstance(suffix, str) and suffix for suffix in suffixes)
            or suffixes[0] == suffixes[1]
        ):
            raise TableMergeSuffixError()

        overlapping = (set(self.columns) & set(other.columns)) - {on}
        left_names = {
            column: f"{column}{suffixes[0]}" if column in overlapping else column
            for column in self.columns
        }
        right_names = {
            column: f"{column}{suffixes[1]}" if column in overlapping else column
            for column in other.columns
            if column != on
        }
        columns = [left_names[column] for column in self.columns]
        columns.extend(right_names[column] for column in other.columns if column != on)
        duplicates = [column for column in dict.fromkeys(columns) if columns.count(column) > 1]
        if duplicates:
            # suffix で既存列を上書きすると値の出所が分からなくなるため、結合前に止める。
            raise TableMergeColumnCollisionError(duplicates)

        right_index = other.index(on)
        rows = []
        for read_row in self._rows:
            write_row = right_index.get(read_row[on])
            if write_row is None and how == "inner":
                continue
            merged = {left_names[column]: read_row[column] for column in self.columns}
            merged.update(
                {
                    right_names[column]: write_row[column] if write_row is not None else ""
                    for column in other.columns
                    if column != on
                }
            )
            rows.append(merged)
        return Table(columns, rows)

    def concat(self, other: "Table") -> "Table":
        """同じ列定義の表を縦に連結する。

        列の順番は異なっていても構わないが、列名の集合が異なる表は
        別のデータとして扱う。列不足を空欄で補うと、入力ミスに気づけず
        データ欠落につながるため、ここでは明示的にエラーにする。
        """
        if set(self.columns) != set(other.columns):
            raise TableError("concatする表の列名が一致しません。")
        columns = self.columns
        return Table(
            columns,
            [{column: row[column] for column in columns} for row in [*self._rows, *other._rows]],
            types=self.types,
        )

    def _check_columns(self, columns: Iterable[str]) -> None:
        missing = [column for column in columns if column not in self.columns]
        if missing:
            raise TableColumnNotFoundError(missing)

    def _iter_rows_for_update(self):
        """ライブラリ内部で更新する実体行を返す。"""
        return iter(self._rows)
