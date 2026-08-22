"""保存先を持たない、初学者向けの表データモデル。

Table はメモリ上の行だけを担当します。CSV や Excel の保存処理をここへ
入れないことで、加工処理とファイル I/O の責任を分けています。
"""

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from comken.exceptions.table import TableError


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
        self.rows = [self._normalize(row) for row in rows]

    def _normalize(self, row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            column: self.types[column](row.get(column, ""))
            if column in self.types
            else row.get(column, "")
            for column in self.columns
        }

    def read(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.rows]

    def __iter__(self):
        return iter(self.rows)

    def __len__(self) -> int:
        return len(self.rows)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, list):
            return self.read() == other
        return super().__eq__(other)

    def replace(self, rows: list[dict]) -> "Table":
        self.rows = [self._normalize(row) for row in rows]
        return self

    def append(self, rows: list[dict] | dict) -> "Table":
        values = [rows] if isinstance(rows, dict) else rows
        self.rows.extend(self._normalize(row) for row in values)
        return self

    def count(self) -> int:
        return len(self.rows)

    def select(self, *columns: str) -> "Table":
        self._check_columns(columns)
        return Table(
            list(columns), [{column: row[column] for column in columns} for row in self.rows]
        )

    def filter(self, predicate: Callable[[dict], bool]) -> "Table":
        return Table(self.columns, [row for row in self.rows if predicate(row)], types=self.types)

    def column(self, name: str) -> list[Any]:
        self._check_columns([name])
        return [row[name] for row in self.rows]

    def index(self, key: str) -> dict[Any, dict]:
        self._check_columns([key])
        return {row[key]: row for row in self.rows}

    def group_by(self, key: str) -> dict[Any, "Table"]:
        grouped: dict[Any, list[dict]] = {}
        for row in self.rows:
            grouped.setdefault(row[key], []).append(row)
        return {
            value: Table(self.columns, rows, types=self.types) for value, rows in grouped.items()
        }

    def merge(self, other: "Table", *, on: str, how: str = "left") -> "Table":
        if how not in {"left", "inner"}:
            raise TableError("merge は left または inner のみ対応します。")
        right_index = other.index(on)
        columns = self.columns + [column for column in other.columns if column not in self.columns]
        rows = []
        for left in self.rows:
            right = right_index.get(left[on])
            if right is None and how == "inner":
                continue
            rows.append(
                {column: (right or {}).get(column, left.get(column, "")) for column in columns}
            )
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
            [
                {column: row.get(column, "") for column in columns}
                for row in [*self.rows, *other.rows]
            ],
            types=self.types,
        )

    def _check_columns(self, columns: Iterable[str]) -> None:
        missing = [column for column in columns if column not in self.columns]
        if missing:
            raise TableError(f"存在しない列です: {missing}")
