"""comken/core/table/model.py — 保存先を持たない、初学者向けの表データモデル。

Table はメモリ上の行だけを担当します。CSV や Excel の保存処理をここへ
入れないことで、加工処理とファイル I/O の責任を分けています。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Iterator, Mapping
from itertools import pairwise
from typing import TYPE_CHECKING, Any, Self

from comken.exceptions.tables import (
    TableColumnNotFoundError,
    TableDuplicateKeyError,
    TableError,
)

if TYPE_CHECKING:
    from comken.core.table.diff import DiffResult, RowChange

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
            raise TableError(
                f"Table の{row_number}件目の列名が columns と一致しません。"
                f"不足列: {missing}、余分な列: {extra}。"
                "\n対処: 不足列と余分な列を直してください。"
                "列を絞る場合は select() を使ってください。"
            )
        normalized = dict(row)
        for column in self.types:
            if column not in self.columns:
                continue
            normalized[column] = self._convert_one(column, row[column], row_number)
        return normalized

    def _convert_one(self, column: str, value: Any, row_number: int) -> Any:
        """``self.types[column]`` で 1 つの値を変換する（``concat()`` からも使う）。"""
        converter = self.types[column]
        try:
            return converter(value)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            raise TableError(
                f"Table の{row_number}件目、列「{column}」の値"
                f"「{value}」を型変換できません。"
                "\n対処: 表示された行番号・列名の値を、"
                "指定した型へ変換できる内容に直してください。"
            ) from exc

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

    def __getitem__(self, index: int) -> dict[str, Any]:
        """指定位置の行をコピーして返す。

        返るのはコピーなので、``table[0]["列"] = x`` と書いても Table は変わらない。
        複数行を欲しいときは ``table.to_rows()[1:]`` のように ``to_rows()`` を使う。
        """
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

    def replace(self, rows: list[dict[str, Any]]) -> Self:
        """表の全行を置き換え、同じTableを返す。"""
        self._rows = [self._normalize(row, row_number) for row_number, row in enumerate(rows, 1)]
        logger.debug("Table replace: %d 行", len(self._rows))
        return self

    def append(self, rows: list[dict[str, Any]] | dict[str, Any]) -> Self:
        """1行または複数行を末尾へ追加する。"""
        values = [rows] if isinstance(rows, dict) else rows
        start = len(self._rows) + 1
        normalized = [self._normalize(row, start + index) for index, row in enumerate(values)]
        self._rows.extend(normalized)
        logger.debug("Table append: +%d 行 (合計 %d 行)", len(normalized), len(self._rows))
        return self

    def select(self, *columns: str, aliases: Mapping[str, str] | None = None) -> Table:
        """指定した列だけを持つ新しいTableを返す。

        aliases に ``{欲しい列名: 実際にこのTableにある列名}`` を渡すと、
        列名が変わっていてもそちらから値を拾う（例えば CSV の見出しが
        リネームされていても、旧名で選び直せる）。結果の列名は常に
        columns 側（欲しい名前）に揃う。aliases に無い列は、そのままの
        名前で存在する前提で選ぶ。
        """
        aliases = aliases or {}
        actual_names = [aliases.get(column, column) for column in columns]
        self._check_columns(actual_names)
        # 選択されなかった列の変換関数まで持ち回らないよう、実際に選んだ
        # 列だけに絞った types を、結果の列名（columns 側）へ付け替えて渡す
        selected_types = {
            column: self.types[actual]
            for column, actual in zip(columns, actual_names, strict=True)
            if actual in self.types
        }
        result = Table._from_normalized_rows(
            list(columns),
            [
                {column: row[actual] for column, actual in zip(columns, actual_names, strict=True)}
                for row in self._rows
            ],
            types=selected_types,
        )
        logger.debug("Table select: %d 列, %d 行", len(result.columns), len(result))
        return result

    def filter(self, predicate: Callable[[dict[str, Any]], bool]) -> Table:
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

    def index(self, key: str) -> dict[Any, dict[str, Any]]:
        """指定列をキーにした行の索引を返す。"""
        self._check_columns([key])
        result: dict[Any, dict[str, Any]] = {}
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
        grouped: dict[Any, list[dict[str, Any]]] = {}
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

        結果の型定義は ``self.types``。``other`` の値は、``other.types``
        に ``self.types`` と**同じ変換関数（``is`` で同一のオブジェクト）**
        が設定されている列はそのまま使い、それ以外は ``self.types`` で変換する
        （変換済みの値に同じ変換を二重にかけないため）。``other.types`` は
        結果に引き継がない。
        """
        if set(self.columns) != set(other.columns):
            raise TableError("concatする表の列名が一致しません。")
        columns = self.columns
        # self 側の行は既に self.types で変換済みなので、再変換しない。
        # other 側の各列について、other.types に同じ変換関数が登録されていれば
        # 変換済みとみなしてそのまま使う（``is`` で同一判定する。非冪等な
        # converter を変換済みの値へ適用するのを避けるため）。
        # other.types に無い列、または別の関数の列は self.types で変換する。
        self_rows = [{column: row[column] for column in columns} for row in self._rows]
        other_rows: list[dict[str, Any]] = []
        for row_number, row in enumerate(other._rows, 1):
            converted: dict[str, Any] = {}
            for column in columns:
                value = row[column]
                if column in self.types and self.types[column] is other.types.get(column):
                    # other 側も同じ converter で変換済み → そのまま使う
                    converted[column] = value
                else:
                    # other が未変換／別関数で変換済み → self.types で揃える
                    converted[column] = self._convert_one(column, value, row_number)
            other_rows.append(converted)
        result = Table._from_normalized_rows(columns, [*self_rows, *other_rows], types=self.types)
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

    def diff(self, other: Table, *, key: str) -> DiffResult:
        """self と other を ``key`` 列で突合し、差分を返す。

        CSV と Excel をまたいだ比較にも使える（"1000" と 1000 は同一視される）。
        正規化後のキーがどちらの表でも重複していたら ``TableDuplicateKeyError``
        を送出する（``Table.index()`` と同じ例外）。

        Args:
            other: 突合先の ``Table``。
            key: 行を一意に識別するキー列名。

        Returns:
            ``DiffResult``（``added`` / ``removed`` は ``Table``、``changed`` は
            ``list[RowChange]``）。
        """
        from comken.core.table.diff import DiffResult, RowChange, diff_row, index_for_diff
        from comken.exceptions import ColumnNotFoundError

        logger.debug(
            "Table diff 開始: self=%d 行, other=%d 行, key=%s",
            len(self),
            len(other),
            key,
        )
        for target in (self, other):
            if key not in target.columns:
                raise ColumnNotFoundError(
                    f"キー列が見つかりません: {key}\n存在する列: {', '.join(target.columns)}"
                    "\n対処: Excel・CSV の列名を確認してください。"
                )
        self_by_key = index_for_diff(self.to_rows(), key)
        other_by_key = index_for_diff(other.to_rows(), key)

        added_rows = [other_by_key[k] for k in other_by_key if k not in self_by_key]
        removed_rows = [self_by_key[k] for k in self_by_key if k not in other_by_key]
        changed = []
        for k in self_by_key:
            if k not in other_by_key:
                continue
            columns = diff_row(self_by_key[k], other_by_key[k])
            if columns:
                changed.append(
                    RowChange(
                        key=k,
                        before=self_by_key[k],
                        after=other_by_key[k],
                        columns=columns,
                    )
                )

        logger.debug(
            "Table diff 完了: added=%d 行, removed=%d 行, changed=%d 行",
            len(added_rows),
            len(removed_rows),
            len(changed),
        )
        return DiffResult(
            added=Table._from_normalized_rows(other.columns, added_rows, types=other.types),
            removed=Table._from_normalized_rows(self.columns, removed_rows, types=self.types),
            changed=changed,
        )

    def changes(self, *, key: str, order_by: str | None = None) -> list[RowChange]:
        """``key`` の値ごとに行を分け、隣り合う行同士を比べる履歴の差分を取る。

        ``key`` の値（``_normalize`` 後）ごとに行を分け、``order_by`` が指定されていれば
        その列の値の**昇順（古い順）**に**安定ソート**してから、**隣り合う行どうし**
        （1番目と2番目、2番目と3番目…）を比べる。値が変わった組だけを
        ``RowChange(key=正規化後のキー, before=前の行, after=次の行, columns=変わった列)``
        で返す。

        比べる列から ``key`` と ``order_by`` の列を除く（変更時刻は毎回違うので、
        含めると全部が「変わった」になる）。

        ``order_by`` が ``None`` なら、並べ替えずに表の並び順のまま比べる。

        返す順: キーが最初に出てきた順、その中は並べ替え後の順。

        Args:
            key: 履歴をまとめるキー列名。
            order_by: 並べ替えに使う列名。``None`` なら表の並び順のまま比べる。

        Returns:
            値が変わった隣り合う行の組 (``RowChange``) のリスト。

        Raises:
            TableColumnNotFoundError: ``key`` / ``order_by`` の列が無いとき。
            TableError: ``order_by`` の列に空 (``None`` / ``""``) の行がある、
                または値の型が混ざっていて比較できない (``TypeError``) とき。
        """
        from comken.core.table.diff import RowChange, _normalize, diff_row

        logger.debug(
            "Table changes 開始: %d 行, key=%s, order_by=%s",
            len(self),
            key,
            order_by,
        )
        columns_to_check = [key] if order_by is None else [key, order_by]
        self._check_columns(columns_to_check)

        rows_by_key: dict[str, list[dict[str, Any]]] = {}
        for row in self._rows:
            normalized_key = _normalize(row[key])
            rows_by_key.setdefault(normalized_key, []).append(row)

        if order_by is not None:
            for rows in rows_by_key.values():
                # 空セル（``None`` / ``""``）は並べ替えの基準にできない。どちらが
                # 古いか決められないため、利用側で埋めてから再実行してもらう。
                empty_index = next(
                    (index for index, row in enumerate(rows) if row[order_by] in (None, "")),
                    None,
                )
                if empty_index is not None:
                    bad_row = rows[empty_index]
                    raise TableError(
                        f"列「{order_by}」に空の行があるため changes() で並べ替えできません。"
                        f"（{key}={bad_row[key]!r}）"
                        "\n対処: 空セルに履歴上の日時を埋めてから実行してください。"
                    )
                try:
                    sorted_rows = sorted(rows, key=lambda r: r[order_by])
                except TypeError as exc:
                    raise TableError(
                        f"列「{order_by}」の値の型が揃っていないため changes() で"
                        f"並べ替えできません。"
                        f"（{key}={rows[0][key]!r}）"
                        "\n対処: 列「{order_by}」の値を文字列か数値に揃えてください。"
                    ) from exc
                rows[:] = sorted_rows

        exclude = {key, order_by} if order_by is not None else {key}
        result: list[RowChange] = []
        for normalized_key, rows in rows_by_key.items():
            if len(rows) < 2:
                continue
            for before_row, after_row in pairwise(rows):
                columns = diff_row(before_row, after_row)
                columns = {col: value for col, value in columns.items() if col not in exclude}
                if columns:
                    result.append(
                        RowChange(
                            key=normalized_key,
                            before=dict(before_row),
                            after=dict(after_row),
                            columns=columns,
                        )
                    )

        logger.debug("Table changes 完了: %d 件", len(result))
        return result

    def _iter_rows_for_update(self) -> Iterator[dict[str, Any]]:
        """ライブラリ内部で更新する実体行を返す。"""
        return iter(self._rows)
