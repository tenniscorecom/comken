"""comken/core/table/model.py — 保存先を持たない表データモデル。

Table はメモリ上の行だけを担当します。CSV や Excel の保存処理をここへ
入れないことで、加工処理とファイル I/O の責任を分けています。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from itertools import pairwise
from typing import TYPE_CHECKING, Any, Self

from comken.core.table.hierarchy import (
    SUBTOTAL_SUFFIXES,
    SUBTOTAL_WORDS,
    HierarchyResult,
    split_hierarchy_rows,
)
from comken.core.text import normalize
from comken.core.types import Row, TypeMap
from comken.exceptions.tables import (
    TableColumnNotFoundError,
    TableDuplicateKeyError,
    TableError,
)

if TYPE_CHECKING:
    from comken.core.table.diff import DiffResult
    from comken.core.table.transfer import TransferResult

logger = logging.getLogger(__name__)


class Table:
    """列と辞書行をメモリで扱う表。

    CSVやExcelに直接依存しないため、加工処理をファイルI/Oから分離できます。
    ``types`` は入力時に明示された列だけを変換し、暗黙の型推測は行いません。
    空の値は ``None`` ではなく空文字 ``""`` にそろえます（``None`` と ``""`` を区別しません）。
    """

    def __init__(
        self,
        columns: list[str] | tuple[str, ...],
        rows: list[Row],
        *,
        types: TypeMap | None = None,
    ) -> None:
        self.columns = list(columns)
        if len(self.columns) != len(set(self.columns)):
            raise TableError("列名は重複させられません。")
        self.types = dict(types or {})
        self._rows: list[Row] = [
            self._normalize(row, row_number) for row_number, row in enumerate(rows, 1)
        ]
        logger.debug(
            "Table 構築: %d 列, %d 行, 型変換 %d 列",
            len(self.columns),
            len(self._rows),
            len(self.types),
        )

    def _normalize(self, row: Mapping[str, Any], row_number: int) -> Row:
        missing = [column for column in self.columns if column not in row]
        extra = [column for column in row if column not in self.columns]
        if missing or extra:
            raise TableError(
                f"Table の{row_number}件目の列名が columns と一致しません。"
                f"不足列: {missing}、余分な列: {extra}。"
                "\n対処: 不足列と余分な列を直してください。"
                "列を絞る場合は select() を使ってください。"
            )
        # 空は ``""`` にそろえる（``None`` と ``""`` を区別しない）。CSV は空欄が ``""``、
        # Excel / Access は ``None`` で返ってくるため、Table に入れる時点で 1 回だけそろえる
        normalized = {column: ("" if value is None else value) for column, value in row.items()}
        for column in self.types:
            if column not in self.columns:
                continue
            normalized[column] = self._convert_one(column, normalized[column], row_number)
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
        rows: list[Row],
        types: TypeMap | None = None,
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

    def to_rows(self) -> list[Row]:
        """現在の行をコピーして返す。元のTableは変更しない。"""
        return [dict(row) for row in self._rows]

    def __getitem__(self, index: int) -> Row:
        """指定位置の行をコピーして返す。

        返るのはコピーなので、``table[0]["列"] = x`` と書いても Table は変わらない。
        複数行を欲しいときは ``table.to_rows()[1:]`` のように ``to_rows()`` を使う。
        """
        return dict(self._rows[index])

    def __iter__(self) -> Iterator[Row]:
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

    def replace(self, rows: list[Row]) -> Self:
        """表の全行を置き換え、同じTableを返す。"""
        self._rows = [self._normalize(row, row_number) for row_number, row in enumerate(rows, 1)]
        logger.debug("Table replace: %d 行", len(self._rows))
        return self

    def append(self, rows: list[Row] | Row) -> Self:
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

    def filter(self, predicate: Callable[[Row], bool]) -> Table:
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

    def index(self, key: str) -> dict[Any, Row]:
        """指定列をキーにした行の索引を返す。"""
        self._check_columns([key])
        result: dict[Any, Row] = {}
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
        grouped: dict[Any, list[Row]] = {}
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

        結果の型定義は ``self.types``。``other`` の値は、``self.types`` に無い列は
        変換せずそのまま使う（``_normalize_row`` と同じく types のある列だけが
        変換対象のため）。``self.types`` にある列は、``other.types`` に
        ``self.types`` と**同じ変換関数（``is`` で同一のオブジェクト）**が
        設定されている列はそのまま使い、それ以外は ``self.types`` で変換する
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
        # self.types に無い列は変換しない（types のない列は _normalize_row で
        # そのまま扱う方針と揃えるため）。それ以外の列は self.types で変換する。
        self_rows = [{column: row[column] for column in columns} for row in self._rows]
        other_rows: list[Row] = []
        for row_number, row in enumerate(other._rows, 1):
            converted: Row = {}
            for column in columns:
                value = row[column]
                if column not in self.types:
                    # self.types に無い列は変換しない（_normalize_row と同じ方針）
                    converted[column] = value
                elif self.types[column] is other.types.get(column):
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
        正規化後の**空でない**キーがどちらの表でも重複していたら
        ``TableDuplicateKeyError`` を送出する（``Table.index()`` と同じ例外）。
        空キー（``normalize`` 後に ``""``。``None``・空白だけを含む）は
        突合対象外で、``self`` の空キー行は ``removed``、``other`` の空キー行は
        ``added`` に、**元表の行順で**入れる。空でないキーの重複は
        ``TableDuplicateKeyError`` で止める（同じ表に空キーが何行あっても
        エラーにならない）。

        Args:
            other: 突合先の ``Table``。
            key: 行を一意に識別するキー列名。

        Returns:
            ``DiffResult``（``added`` / ``removed`` / ``changed`` のどれも ``Table``）。
            ``changed`` は 1 行 = 1 セルの変更で、列は ``key`` / ``列`` / ``変更前`` /
            ``変更後``（1 つの行で 2 列が変わっていれば 2 行になる）。``key`` の値は
            正規化後の文字列。
        """
        from comken.core.table.diff import DiffResult, changes_table, diff_row, index_for_diff
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
        self_rows = self.to_rows()
        other_rows = other.to_rows()
        self_by_key = index_for_diff(self_rows, key)
        other_by_key = index_for_diff(other_rows, key)

        # 空キー行は索引化されない（index_for_diff の挙動）ので、``added`` /
        # ``removed`` には元表を順に見て「空キーまたは相手側にキーが無い行」を
        # 集める。``index_for_diff`` は行順を保った dict を返すので、
        # キーが無い行を相手側の索引から順に取り出す形でも元表順が保たれる。
        removed_rows = [
            row
            for row in self_rows
            if normalize(row[key]) == "" or normalize(row[key]) not in other_by_key
        ]
        added_rows = [
            row
            for row in other_rows
            if normalize(row[key]) == "" or normalize(row[key]) not in self_by_key
        ]
        changed_cells: list[tuple[str, Any, dict[str, tuple[Any, Any]]]] = []
        for k, self_row in self_by_key.items():
            other_row = other_by_key.get(k)
            if other_row is None:
                continue
            columns = diff_row(self_row, other_row)
            if columns:
                changed_cells.append((k, None, columns))
        changed = changes_table(key, changed_cells)

        logger.debug(
            "Table diff 完了: added=%d 行, removed=%d 行, changed=%d セル",
            len(added_rows),
            len(removed_rows),
            len(changed),
        )
        return DiffResult(
            added=Table._from_normalized_rows(other.columns, added_rows, types=other.types),
            removed=Table._from_normalized_rows(self.columns, removed_rows, types=self.types),
            changed=changed,
        )

    def transfer_from(
        self,
        read: Table,
        mapping: Mapping[str, str],
        *,
        read_key: str | Sequence[str],
        write_key: str | Sequence[str],
        where: Callable[[Row, Row], bool] | None = None,
    ) -> TransferResult:
        """``self``（転記先）に ``read``（転記元）をキー突合で転記する。

        ``self`` を Excel の表、``read`` を CSV の表だと思えば ``excel_table
        .transfer_from(csv_table, ...)`` と書けて、「Excel の表が CSV の表から
        転記を受ける」と向きが読める。``Table.diff()`` と同じく薄いメソッドで、
        コア処理は ``comken.core.table.transfer.transfer_tables`` に置く。

        1 回の呼び出しで「突合 → 転記 → 未一致行の収集」がすべて揃う。
        条件は ``where=`` に書く。結果は ``TransferResult``（``table`` /
        ``only_in_read`` / ``only_in_write`` / ``matched_count`` /
        ``transferred_count``）にまとめ、どれも新しい ``Table`` か数にして、
        入力とは辞書を共有しない。キーの重複は ``read`` / ``self`` のどちらも
        エラーになる（``TableDuplicateKeyError``）。

        Args:
            read: 転記元の ``Table``。変更しない。
            mapping: 「転記元の列名 → ``self`` の列名」の ``Mapping``。 1 個以上必須。
            read_key: ``read`` のキー列。 ``str`` なら 1 列、 ``Sequence[str]`` なら複合キー。
            write_key: ``self`` のキー列。 ``read_key`` と同じ要素数でなければならない。
            where: 任意の追加条件 ``(read_row, write_row) -> bool``。 ``True`` のときだけ
                転記する。 受け取るのはコピー（書き換えても結果にも入力にも影響しない）。
                判定だけ書く（行を直す処理は書かない）。 ログ出力は可。 例外はそのまま
                伝わる。 未一致の行では呼ばれない。 1 組につき 1 回。

        Returns:
            ``TransferResult``。 ``table`` が転記後の ``Table``（``self`` と同じ
            列・同じ行順・同じ行数の新しい ``Table``）、 ``only_in_read`` /
            ``only_in_write`` が未一致の行、 ``matched_count`` / ``transferred_count``
            が一致数と転記数。

        Raises:
            InvalidTableInputError: ``read`` が ``Table`` でない。
            TableError: ``mapping`` が空、 ``read_key`` と ``write_key`` の要素数が違う、
                ``mapping`` の転記先列が重複している。
            TableColumnNotFoundError: ``mapping`` の転記元列・転記先列、
                ``read_key`` / ``write_key`` の列が存在しない（データを読む前に出る）。

        Note:
            セルの値は ``str`` / ``int`` / ``float`` / ``bool`` / ``datetime`` などの
            **不変の値であること** を前提とする。 ``list`` や ``dict`` など変更可能な値を
            セルに入れた場合、浅いコピーによる共有は保証しない。

            ``result.table`` は転記した値に ``self.types`` の変換を 1 回かける。
            転記しなかった行・列には変換関数を再適用しない（呼び出し回数が増える不具合を
            防ぐため）。 ``self.types`` に無い列は変換しない。 変換できない値は
            ``TableError``（行番号・列名・値が出る）。

        Example:
            通常の転記::

                from comken.core.table import Table
                result = excel_table.transfer_from(
                    csv_table, mapping={"顧客名": "name", "金額": "amount"},
                    read_key="顧客ID", write_key="id",
                )
                result_table = result.table

            ``where`` で条件を満たす行だけ転記::

                def is_confirmed(read_row, write_row):
                    return read_row["金額"] > 0
                result = excel_table.transfer_from(
                    csv_table, mapping, read_key="id", write_key="id", where=is_confirmed,
                )

            未一致の行を別途処理する::

                for read_row in result.only_in_read:
                    ...  # read 側にしか無い行（self への新規追加候補）

                for write_row in result.only_in_write:
                    ...  # self 側にしか無い行（破棄候補）
        """
        from comken.core.table.transfer import transfer_tables

        return transfer_tables(
            read,
            self,
            mapping,
            read_key=read_key,
            write_key=write_key,
            where=where,
        )

    def split_hierarchy(
        self,
        levels: list[str] | tuple[str, ...],
        *,
        subtotal_words: Iterable[str] = SUBTOTAL_WORDS,
        subtotal_suffixes: Iterable[str] = SUBTOTAL_SUFFIXES,
    ) -> HierarchyResult:
        """階層の列を上の階層で埋め、小計の行を分けて ``HierarchyResult`` を返す。

        Excel で多い次のパターンを扱うための関数:

        - 上の階層はグループの最初の行にしか値が無い（下は空欄）
        - 途中に「小計」「合計」「野菜計」のような小計の行が挟まっている

        上の階層（``levels`` の前の方）に値があれば、その下の階層の ``current`` を
        空に戻し、前の中分類を持ち越さない。小計の判定は ``subtotal_words``
        との完全一致、``subtotal_suffixes`` の末尾一致、「現在のグループの
        代表名 + 計」の3段構えで、「計」で終わるだけの値（時計・会計など）は
        小計にしない。元の Table は変えない（新しい Table を返す）。

        Args:
            levels: 階層の列名（上から順）。1 つ以上。
            subtotal_words: 小計と完全一致で扱う値の iterable。既定は
                ``SUBTOTAL_WORDS = ("計", "小計", "合計", "総計")``。
            subtotal_suffixes: 小計として扱う接尾辞の iterable。既定は
                ``SUBTOTAL_SUFFIXES = ("小計", "合計", "総計")``。

        Returns:
            ``HierarchyResult``（``details`` / ``subtotals`` は ``Table``、
            ``unmatched`` は「計」で終わる値があるのに小計と判定しなかった行の
            件目（1始まり））。

        Raises:
            TableColumnNotFoundError: ``levels`` の列が存在しない。
            TableError: 階層の列に Excel のエラー値（``#REF!`` 等）がある。

        Example:
            >>> table = Table(
            ...     ["大分類", "中分類", "小分類", "金額"],
            ...     [
            ...         {"大分類": "食品", "中分類": "野菜", "小分類": "にんじん", "金額": 100},
            ...         {"大分類": None,   "中分類": None,   "小分類": "たまねぎ", "金額": 50},
            ...         {"大分類": None,   "中分類": "野菜計", "小分類": None,   "金額": 150},
            ...     ],
            ... )
            >>> result = table.split_hierarchy(["大分類", "中分類", "小分類"])
            >>> len(result.details)
            2
            >>> len(result.subtotals)
            1
        """
        levels_list = list(levels)
        self._check_columns(levels_list)
        if not levels_list:
            raise TableError("levels は 1 つ以上必要です。")
        words = tuple(subtotal_words)
        suffixes = tuple(subtotal_suffixes)
        logger.debug(
            "Table split_hierarchy 開始: %d 行, levels=%s",
            len(self),
            levels_list,
        )
        details_rows, subtotal_rows, unmatched = split_hierarchy_rows(
            self._rows,
            levels_list,
            subtotal_words=words,
            subtotal_suffixes=suffixes,
        )
        details = Table._from_normalized_rows(self.columns, details_rows, types=self.types)
        subtotals = Table._from_normalized_rows(self.columns, subtotal_rows, types=self.types)
        logger.debug(
            "Table split_hierarchy 完了: details=%d 行, subtotals=%d 行, unmatched=%d 行",
            len(details),
            len(subtotals),
            len(unmatched),
        )
        return HierarchyResult(details=details, subtotals=subtotals, unmatched=unmatched)

    def changes(self, *, key: str, order_by: str | None = None) -> Table:
        """``key`` の値ごとに行を分け、隣り合う行同士を比べる履歴の差分を取る。

        ``key`` の値（``normalize`` 後）ごとに行を分け、``order_by`` が指定されていれば
        その列の値の**昇順（古い順）**に**安定ソート**してから、**隣り合う行どうし**
        （1番目と2番目、2番目と3番目…）を比べる。値が変わったセルだけを、
        1 行 = 1 セルの ``Table`` で返す（列は ``key`` / ``order_by``（指定したとき。
        変更後の行の値）/ ``列`` / ``変更前`` / ``変更後``。``key`` の値は正規化後の文字列）。

        比べる列から ``key`` と ``order_by`` の列を除く（変更時刻は毎回違うので、
        含めると全部が「変わった」になる）。

        ``order_by`` が ``None`` なら、並べ替えずに表の並び順のまま比べる。

        返す順: キーが最初に出てきた順、その中は並べ替え後の順。

        空キー（``normalize`` 後に ``""``。``None``・空白だけを含む）の行は
        **無視する**。``Table.diff()`` / ``Table.transfer_from()`` と同じ規則で、
        空キー行は重複検査の対象にもならない。``order_by`` が空の空キー行も
        エラーにしない（そもそも対象から除かれるため）。

        Args:
            key: 履歴をまとめるキー列名。
            order_by: 並べ替えに使う列名。``None`` なら表の並び順のまま比べる。

        Returns:
            値が変わったセルの ``Table``（``Table.diff()`` の ``changed`` と同じ形）。

        Raises:
            TableColumnNotFoundError: ``key`` / ``order_by`` の列が無いとき。
            TableError: ``order_by`` の列に空 (``None`` / ``""``) の行がある、
                または値の型が混ざっていて比較できない (``TypeError``) とき。
        """
        from comken.core.table.diff import changes_table, diff_row

        logger.debug(
            "Table changes 開始: %d 行, key=%s, order_by=%s",
            len(self),
            key,
            order_by,
        )
        columns_to_check = [key] if order_by is None else [key, order_by]
        self._check_columns(columns_to_check)

        rows_by_key: dict[str, list[Row]] = {}
        for row in self._rows:
            normalized_key = normalize(row[key])
            # 空キー行は changes() の対象外（diff() / Table.transfer_from() と同じ規則）
            if normalized_key == "":
                continue
            rows_by_key.setdefault(normalized_key, []).append(row)

        if order_by is not None:
            for rows in rows_by_key.values():
                self._sort_changes_group(rows, order_by, key)

        exclude = {key, order_by} if order_by is not None else {key}
        changed_cells: list[tuple[str, Any, dict[str, tuple[Any, Any]]]] = []
        for normalized_key, rows in rows_by_key.items():
            if len(rows) < 2:
                continue
            for before_row, after_row in pairwise(rows):
                columns = diff_row(before_row, after_row)
                columns = {col: value for col, value in columns.items() if col not in exclude}
                if columns:
                    order_value = after_row[order_by] if order_by is not None else None
                    changed_cells.append((normalized_key, order_value, columns))
        result = changes_table(key, changed_cells, order_by=order_by)

        logger.debug("Table changes 完了: %d セル", len(result))
        return result

    @staticmethod
    def _sort_changes_group(rows: list[Row], order_by: str, key: str) -> None:
        """``changes()`` の 1 キー分の行を ``order_by`` 昇順で並べ替える（内部用）。

        ``order_by`` 列に空（``None`` / ``""``）の行がある、または値の型が混ざって
        いて ``sorted`` が ``TypeError`` を出すときは ``TableError`` に変換する。
        rows は破壊的にソートされる。
        """
        # 空セル（``None`` / ``""``）は並べ替えの基準にできない。どちらが
        # 古いか決められないため、利用側で埋めてから再実行してもらう。
        # 空キー行は既に除外済みなので、ここで空になるのは空でないキーの行だけ。
        empty_index = next(
            (index for index, row in enumerate(rows) if row[order_by] == ""),
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
                f"\n対処: 列「{order_by}」の値を文字列か数値に揃えてください。"
            ) from exc
        rows[:] = sorted_rows
