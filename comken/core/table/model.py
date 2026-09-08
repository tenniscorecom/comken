"""comken/core/table/model.py — 保存先を持たない、初学者向けの表データモデル。

Table はメモリ上の行だけを担当します。CSV や Excel の保存処理をここへ
入れないことで、加工処理とファイル I/O の責任を分けています。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Iterator, Mapping
from typing import Any, Self

from comken.exceptions.table import (
    TableColumnNotFoundError,
    TableDuplicateKeyError,
    TableError,
    TableRowColumnsError,
    TableTypeConversionError,
)

logger = logging.getLogger(__name__)


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
        logger.debug(
            "Table 構築: %d 列, %d 行, 型変換 %d 列",
            len(self.columns),
            len(self._rows),
            len(self.types),
        )

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

    @classmethod
    def _from_normalized_rows(
        cls,
        columns: list[str] | tuple[str, ...],
        rows: list[dict[str, Any]],
        types: Mapping[str, Callable[[Any], Any]] | None = None,
    ) -> Table:
        """既に types 変換済みの行から Table を作る（変換関数を再実行しない内部専用）。

        select() / filter() / group_by() / concat() のように、値が既に元の
        Table で変換済みであることを呼び出し側が保証できるときだけ使う。
        通常の ``Table(...)`` と違い ``_normalize()`` を通さないため、列の
        過不足チェックも行わない（呼び出し側の責任で ``columns`` と ``rows`` の
        列が一致していること）。

        渡された行は ``dict(row)`` でコピーしてから保持する（Table 間で行
        オブジェクトの参照を共有しない、という既存の不変条件を保つため）。
        """
        instance = cls.__new__(cls)
        instance.columns = list(columns)
        if len(instance.columns) != len(set(instance.columns)):
            raise TableError("列名は重複させられません。")
        instance.types = dict(types or {})
        instance._rows = [dict(row) for row in rows]
        return instance

    def to_rows(self) -> list[dict[str, Any]]:
        """現在の行をコピーして返す。元のTableは変更しない。"""
        return [dict(row) for row in self._rows]

    def __getitem__(self, index: int | slice) -> dict[str, Any] | list[dict[str, Any]]:
        """指定位置の行、または行のスライスをコピーして返す。

        返るのはコピーなので、``table[0]["列"] = x`` と書いても Table は変わらない。
        """
        if isinstance(index, slice):
            return [dict(row) for row in self._rows[index]]
        return dict(self._rows[index])

    def __iter__(self) -> Iterator[dict[str, Any]]:
        """各行のコピーを返す。反復中の変更は元のTableへ反映しない。"""
        for row in self._rows:
            yield dict(row)

    def __len__(self) -> int:
        return len(self._rows)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Table):
            # ``columns`` の**順番**が違う ``Table`` は等しくない（``concat`` が
            # 列順を揃える設計と揃える）。 ``types`` は比較に含めない（変換関数は
            # 表の中身ではないため）。
            return self.columns == other.columns and self.to_rows() == other.to_rows()
        if isinstance(other, list):
            return self.to_rows() == other
        # それ以外の型とは比較しない（``list`` を「中身の ``dict``」と誤判定しない
        # よう ``__eq__`` で ``False`` を返さず ``NotImplemented`` を返す）
        return NotImplemented

    def replace(self, rows: list[dict]) -> Self:
        """表の全行を置き換え、同じTableを返す。"""
        self._rows = [self._normalize(row, row_number) for row_number, row in enumerate(rows, 1)]
        logger.debug("Table replace: %d 行", len(self._rows))
        return self

    def append(self, rows: list[dict] | dict) -> Self:
        """1行または複数行を末尾へ追加する。"""
        values = [rows] if isinstance(rows, dict) else rows
        start = len(self._rows) + 1
        normalized = [self._normalize(row, start + index) for index, row in enumerate(values)]
        self._rows.extend(normalized)
        logger.debug("Table append: +%d 行 (合計 %d 行)", len(normalized), len(self._rows))
        return self

    def select(self, *columns: str) -> Table:
        """指定した列だけを持つ新しいTableを返す。"""
        self._check_columns(columns)
        # 選択されなかった列の変換関数まで持ち回らないよう、columns に含まれる
        # 列だけに絞った types を渡す
        selected_types = {
            column: converter for column, converter in self.types.items() if column in columns
        }
        result = Table._from_normalized_rows(
            list(columns),
            [{column: row[column] for column in columns} for row in self._rows],
            types=selected_types,
        )
        logger.debug("Table select: %d 列, %d 行", len(result.columns), len(result))
        return result

    def filter(self, predicate: Callable[[dict], bool]) -> Table:
        """条件に一致する行だけを持つ新しいTableを返す。"""
        # predicate は利用者コードなので、渡すのはコピー（誤って行を書き換えても
        # 元の Table へ影響させない）。採用した行そのもの（コピーではない）を
        # rows へ集め、コピーは _from_normalized_rows() 側の1回だけにする
        # （以前は predicate 用・採用時・fast path 内の3重コピーになっていた）。
        rows = [row for row in self._rows if predicate(dict(row))]
        result = Table._from_normalized_rows(self.columns, rows, types=self.types)
        logger.debug("Table filter: %d 行 (元 %d 行)", len(result), len(self._rows))
        return result

    def column(self, name: str) -> list[Any]:
        """指定列の値を順番どおりに返す。"""
        self._check_columns([name])
        return [row[name] for row in self._rows]

    def index(self, key: str) -> dict[Any, dict]:
        """指定列をキーにした行の索引を返す。"""
        self._check_columns([key])
        result: dict[Any, dict] = {}
        for row in self._rows:
            value = row[key]
            if value in result:
                logger.debug("Table index: キー重複を検出: %s=%r", key, value)
                raise TableDuplicateKeyError([key], value)
            result[value] = dict(row)
        logger.debug("Table index: %s で索引化, %d 件", key, len(result))
        return result

    def group_by(self, key: str) -> dict[Any, Table]:
        """指定列の値ごとにTableを分けて返す。"""
        self._check_columns([key])
        grouped: dict[Any, list[dict]] = {}
        for row in self._rows:
            grouped.setdefault(row[key], []).append(row)
        result = {
            value: Table._from_normalized_rows(self.columns, rows, types=self.types)
            for value, rows in grouped.items()
        }
        logger.debug("Table group_by: %s で %d グループ", key, len(result))
        return result

    def concat(self, other: Table) -> Table:
        """同じ列定義の表を縦に連結する。

        列の順番は異なっていても構わないが、列名の集合が異なる表は
        別のデータとして扱う。列不足を空欄で補うと、入力ミスに気づけず
        データ欠落につながるため、ここでは明示的にエラーにする。
        """
        if set(self.columns) != set(other.columns):
            raise TableError("concatする表の列名が一致しません。")
        columns = self.columns
        # ``other`` は自分と別の Table なので types が異なりうる。
        # _from_normalized_rows() は変換済み前提で converter を実行しないため、
        # ``other`` 側の値を self.types で変換し直さずに混ぜてしまうと、
        # 同じ列に self.types 変換済みの値と未変換の値が混在しうる。
        # concat() だけは通常の ``Table(...)`` を使い、self.types を全行へ
        # 揃えて適用する（既存の挙動を維持する）。
        result = Table(
            columns,
            [{column: row[column] for column in columns} for row in [*self._rows, *other._rows]],
            types=self.types,
        )
        logger.debug(
            "Table concat: %d 行 + %d 行 = %d 行",
            len(self._rows),
            len(other._rows),
            len(result),
        )
        return result

    def _check_columns(self, columns: Iterable[str]) -> None:
        missing = [column for column in columns if column not in self.columns]
        if missing:
            raise TableColumnNotFoundError(missing)

    def _iter_rows_for_update(self) -> Iterator[dict[str, Any]]:
        """ライブラリ内部で更新する実体行を返す。"""
        return iter(self._rows)
