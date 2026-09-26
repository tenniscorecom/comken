"""comken/core/table/diff.py — 行・表の差分を取る部品。

``diff_row``（行どうし）と、``Table.diff()`` / ``Table.changes()`` の結果である
``RowChange`` / ``DiffResult`` を置く。``model.py`` との循環 import を避けるため、
``Table`` の注釈は ``from __future__ import annotations`` + ``TYPE_CHECKING`` で参照する。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from comken.core.table.model import Table


def diff_row(before: dict[str, Any], after: dict[str, Any]) -> dict[str, tuple[Any, Any]]:
    """1行同士を比較し、値が異なる列だけを {列名: (変更前, 変更後)} で返す。

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
class RowChange:
    """``Table.diff()`` / ``Table.changes()`` が返す「変更のあった行」の情報。

    Attributes:
        key: キー列の正規化後の値（``_normalize`` を通した文字列）。
        before: 変更前の行全体。
        after: 変更後の行全体。
        columns: 変わった列だけ {列名: (変更前, 変更後)}。
    """

    key: str
    before: dict[str, Any]
    after: dict[str, Any]
    columns: dict[str, tuple[Any, Any]]


@dataclass
class DiffResult:
    """``Table.diff()`` の結果。

    なぜ ``added`` / ``removed`` が ``Table`` で ``changed`` が ``list[RowChange]``
    なのか — ``changed`` の1件は「変更前・変更後・差分列」の3つを抱えており、
    表の1行に収まらない（同じ列名で2つの値を並べると区別できない）ため
    ``RowChange`` のリストのままで持つ。 一方 ``added`` / ``removed`` は表の行と
    同じ形なので ``Table`` へ揃え、 ``filter`` / ``select`` / ``count`` などの
    Table 標準の操作が直接使えるようにしてある。
    """

    added: Table  # other にだけある行（other の列構成）
    removed: Table  # self にだけある行（self の列構成）
    changed: list[RowChange]  # キーが一致して値が変わった行


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
    rows: list[dict[str, Any]],
    key: str,
) -> dict[str, dict[str, Any]]:
    """``Table.diff()`` のために、``_normalize`` 後のキーで索引化する。

    正規化後のキーが重複していたら ``TableDuplicateKeyError`` を送出する
    （``Table.index()`` と同じ例外）。
    """
    from comken.exceptions.tables import TableDuplicateKeyError

    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        normalized_key = _normalize(row[key])
        if normalized_key in index:
            raise TableDuplicateKeyError([key], normalized_key)
        index[normalized_key] = row
    return index


__all__ = ["diff_row", "RowChange", "DiffResult"]
