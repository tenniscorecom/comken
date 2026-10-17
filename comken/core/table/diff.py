"""comken/core/table/diff.py — 行・表の差分を取る部品。

``Table.diff()`` の結果である ``DiffResult`` と、1 行どうしを比べる ``diff_row``
（``Table.diff()`` / ``Table.changes()`` の内部で使う）を置く。変更のあった値は
``Table``（1 行 = 1 セルの変更）で返し、専用のクラスは増やさない。
``model.py`` との循環 import を避けるため、``Table`` の注釈は
``from __future__ import annotations`` + ``TYPE_CHECKING`` で参照する。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from comken.core.text import normalize
from comken.core.types import Row
from comken.exceptions.tables import TableError

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from comken.core.table.model import Table


def diff_row(before: Row, after: Row) -> dict[str, tuple[Any, Any]]:
    """1行同士を比較し、値が異なる列だけを {列名: (変更前, 変更後)} で返す（内部用）。

    CSV の str と Excel の数値は同一視する（"1000" と 1000 は差分にならない）。
    片方にしか存在しない列は、もう片方を空文字（``""``）に揃えて比較する。

    先頭ゼロ付きの文字列（社員番号 "0001" 等）は数値化しない。
    "0001" と 1 は別の値として差分になる（先頭ゼロの消失を検出できる）。
    Args:
        before: 変更前の行（辞書）。
        after: 変更後の行（辞書）。

    Returns:
        {列名: (変更前の値, 変更後の値)} の辞書。値は元の型のまま返す。
    """
    result = {}
    for col in {**before, **after}:
        old, new = before.get(col, ""), after.get(col, "")
        if normalize(old) != normalize(new):
            result[col] = (old, new)
    return result


@dataclass
class DiffResult:
    """``Table.diff()`` の結果。3 つとも ``Table`` で、``filter`` / ``select`` / ``count`` などの
    Table 標準の操作がそのまま使える。

    ``changed`` は **1 行 = 1 セルの変更** の表。
    列は ``キー列`` / ``列`` / ``変更前`` / ``変更後``。
    1 つの行で 2 つの列が変わっていれば 2 行になる。「前」と「後」を 2 つ組（タプル）や
    専用のクラスで持たず、列名で読めるようにしてある。
    """

    added: Table  # other にだけある行（other の列構成）
    removed: Table  # self にだけある行（self の列構成）
    changed: Table  # キーが一致して値が変わったセル（キー列 / 列 / 変更前 / 変更後）


# ``DiffResult.changed`` / ``Table.changes()`` の表の、変更の中身を表す列名
CHANGE_COLUMN = "列"
BEFORE_COLUMN = "変更前"
AFTER_COLUMN = "変更後"


def changes_table(
    key: str,
    changes: list[tuple[str, Any, dict[str, tuple[Any, Any]]]],
    *,
    order_by: str | None = None,
) -> Table:
    """変更のあったセルを、1 行 = 1 セルの ``Table`` にする（``diff`` / ``changes`` の内部用）。

    列は ``[key]``（``order_by`` を渡すと続けて ``[order_by]``）と、
    ``列`` / ``変更前`` / ``変更後``。

    Args:
        key: キー列の名前。
        changes: ``(キーの値, order_by の値, diff_row() の結果)`` のリスト。
        order_by: 履歴の並べ替えに使った列の名前。渡すと、その列の値（変更後の行のもの）も入れる。
    """
    from comken.core.table.model import Table

    columns = [key, *([order_by] if order_by is not None else []), CHANGE_COLUMN]
    columns += [BEFORE_COLUMN, AFTER_COLUMN]
    if len(columns) != len(set(columns)):
        raise TableError(
            f"キー列「{key}」"
            + (f"・並べ替えの列「{order_by}」" if order_by else "")
            + f"の名前が、差分の表の列名（{CHANGE_COLUMN} / {BEFORE_COLUMN} / {AFTER_COLUMN}）と"
            "重なっています。\n対処: 列の名前を変えてから比べてください。"
        )
    rows = []
    for key_value, order_value, cells in changes:
        for column, (before, after) in cells.items():
            row = {key: key_value}
            if order_by is not None:
                row[order_by] = order_value
            row |= {CHANGE_COLUMN: column, BEFORE_COLUMN: before, AFTER_COLUMN: after}
            rows.append(row)
    return Table(columns, rows)


def index_by_key(
    rows: list[Row],
    columns: list[str],
) -> dict[tuple[str, ...], Row]:
    """正規化後のキーで索引を作る（``Table.diff()`` / ``transfer()`` の共通部品）。

    キーは ``normalize()`` でそろえた後、各列の値を並べた ``tuple[str, ...]``。
    戻り値の辞書は、そのタプルをキーに ``Row`` を引く形になる。

    空キー（``normalize`` 後に ``""`` の要素が 1 つでもある）は索引に入れない。
    ``Table.diff()`` / ``Table.changes()`` / ``transfer()`` のいずれも空キーは
    突合対象外で揃えており、ここでも同じ規則で空キーを除く。空キー行は呼び出し側
    （``Table.diff()`` / ``transfer()``）が ``added`` / ``removed`` /
    ``only_in_*`` 側へ集める。

    正規化後の**空でない**キーが重複していたら ``TableDuplicateKeyError``
    を送出する（``Table.index()`` と同じ例外）。複合キーは列名のリストを渡し、
    キー値は ``","`` で連結してメッセージに出す。

    Args:
        rows: 索引対象の行のリスト。
        columns: キー列のリスト（順序を保って ``tuple`` にする）。
    """
    from comken.exceptions.tables import TableDuplicateKeyError

    index: dict[tuple[str, ...], Row] = {}
    for row in rows:
        key = tuple(normalize(row[column]) for column in columns)
        if any(value == "" for value in key):
            continue
        if key in index:
            raise TableDuplicateKeyError(list(columns), ",".join(key))
        index[key] = row
    return index


def index_for_diff(
    rows: list[Row],
    key: str,
) -> dict[str, Row]:
    """``Table.diff()`` のために、``normalize`` 後のキーで索引化する。

    正規化後のキーが重複していたら ``TableDuplicateKeyError`` を送出する
    （``Table.index()`` と同じ例外）。空キー行は索引に入らない
    （``Table.diff()`` は空キー行を ``added`` / ``removed`` 側へ集めるため、
    索引化対象から除く）。

    ``index_by_key`` の薄いラッパーで、戻り値のキーを単一文字列に展開して返す。
    """
    return {key_tuple[0]: row for key_tuple, row in index_by_key(rows, [key]).items()}


__all__ = ["DiffResult"]
