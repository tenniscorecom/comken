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

from comken.core.table.row import Row
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
        old, new = before.get(col), after.get(col)
        if _normalize(old) != _normalize(new):
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


def _normalize(value: object) -> str:
    """比較用に値を文字列へ揃える。

    CSV は全部 str、Excel は int / float / None で返ってくるため、
    そのまま == で比べると「"1000" と 1000」が差分扱いになってしまう。
    None は ""、整数値の float（1000.0）は int（1000）を経由して文字列にする。

    こちらは行の比較用で None を "" に揃える役割を持つ。
    """
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def index_for_diff(
    rows: list[Row],
    key: str,
) -> dict[str, Row]:
    """``Table.diff()`` のために、``_normalize`` 後のキーで索引化する。

    正規化後のキーが重複していたら ``TableDuplicateKeyError`` を送出する
    （``Table.index()`` と同じ例外）。
    """
    from comken.exceptions.tables import TableDuplicateKeyError

    index: dict[str, Row] = {}
    for row in rows:
        normalized_key = _normalize(row[key])
        if normalized_key in index:
            raise TableDuplicateKeyError([key], normalized_key)
        index[normalized_key] = row
    return index


__all__ = ["DiffResult"]
