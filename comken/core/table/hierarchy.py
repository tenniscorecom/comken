"""comken/core/table/hierarchy.py — 階層列の上埋めと小計行の分離。

Excel で多い次のパターンを扱う:

- 上の階層はグループの最初の行にしか値が無い（下は空欄）
- 途中に「小計」「合計」「野菜計」のような小計の行が挟まっている

``Table.split_hierarchy()`` が ``HierarchyResult`` （details / subtotals /
unmatched）に分ける。``model.py`` との循環 import を避けるため、
``Table`` の注釈は ``from __future__ import annotations`` + ``TYPE_CHECKING`` で参照する
（``diff.py`` と同じパターン）。

「計」で終わる値だけ（時計・会計など）を小計にしないため、ルールの組み立ては
``SUBTOTAL_WORDS`` と ``SUBTOTAL_SUFFIXES`` の2段構えにする。さらにグループの
current + 計（例: 現在の大分類が「野菜」のときの「野菜計」）も拾う。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from comken.exceptions.tables import TableError

if TYPE_CHECKING:
    from comken.core.table.model import Table

logger = logging.getLogger(__name__)

# Excel のエラー値文字列。階層列で見つけたら TableError にする。
# 階層以外の列（金額など）にあればそのまま明細に出す
# （``_check_excel_errors`` の対象外なので下流にそのまま流れる）。
_EXCEL_ERROR_VALUES: frozenset[str] = frozenset(
    {
        "#NULL!",
        "#DIV/0!",
        "#VALUE!",
        "#REF!",
        "#NAME?",
        "#NUM!",
        "#N/A",
    }
)

# 小計と完全一致で拾う語。``SUBTOTAL_SUFFIXES`` との重複は気にしない
# （完全一致の方が先に判定され short-circuit で返るため）。
SUBTOTAL_WORDS: tuple[str, ...] = ("計", "小計", "合計", "総計")

# 小計として扱う接尾辞。末尾一致なので「野菜小計」「食品 合計」が拾える一方、
# 純粋な「計」のみ（例: 時計）は拾わない（ルール3の current + 計が当たる場合のみ）。
SUBTOTAL_SUFFIXES: tuple[str, ...] = ("小計", "合計", "総計")


@dataclass
class HierarchyResult:
    """``Table.split_hierarchy()`` の結果。

    ``details`` / ``subtotals`` は ``Table`` なので、``select / filter / count``
    などの Table 標準の操作が直接使える（``DiffResult`` と同じ意図の設計）。

    Attributes:
        details: 明細の行（全階層が current で埋まった状態）。
        subtotals: 小計の行。matched level より上は current、matched level は
            元の値、下は None。
        unmatched: 「計」で終わる値があるのに小計と判定しなかった行の
            **件目**（1始まり、元の Table の何件目か）。
    """

    details: Table
    subtotals: Table
    unmatched: list[int]


def _is_empty_value(value: Any) -> bool:
    """値が「空」とみなせるか判定する。

    None と、strip すると空文字になる str を空扱いとする
    （数値は False 扱い。``0`` 自体は値あり）。
    """
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def _strip_value(value: Any) -> str:
    """比較用に ``str(value).strip()`` する。None は ``""`` 扱い。

    ``float`` で整数値（``is_integer()`` が真）のものは ``int`` 化してから文字列にする
    （Excel COM が整数を ``10.0`` で返すため、current=10.0 のときの「10計」が
    「10.0計」と比較されて外れるのを防ぐ）。小数点付き（``10.5`` 等）はそのまま。
    """
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _matches_subtotal(
    value: Any,
    current: list[Any],
    subtotal_words: tuple[str, ...],
    subtotal_suffixes: tuple[str, ...],
) -> bool:
    """値が小計のルール 1, 2, 3 のどれかに当てはまるか判定する。

    Args:
        value: 判定対象のセル値。
        current: 各階層の現在の値（上位から順）。
        subtotal_words: ルール1で完全一致を見る値のタプル。
        subtotal_suffixes: ルール2で末尾一致を見る値のタプル。
    """
    stripped = _strip_value(value)
    if stripped in subtotal_words:
        return True
    for suffix in subtotal_suffixes:
        if stripped.endswith(suffix):
            return True
    for c_value in current:
        if c_value is None:
            continue
        if stripped == _strip_value(c_value) + "計":
            return True
    return False


def _find_topmost_subtotal_level(
    row: dict[str, Any],
    levels: list[str],
    current: list[Any],
    subtotal_words: tuple[str, ...],
    subtotal_suffixes: tuple[str, ...],
) -> int | None:
    """小計と判定される一番上の階層のインデックスを返す。なければ None。

    「2 つ以上の列に小計の言葉があれば、一番上の階層の列を基準にする」
    の規約に従う。
    """
    for level_idx, level_name in enumerate(levels):
        if _matches_subtotal(row[level_name], current, subtotal_words, subtotal_suffixes):
            return level_idx
    return None


def _check_excel_errors(
    row: dict[str, Any],
    levels: list[str],
    row_number: int,
) -> None:
    """階層の列に Excel のエラー値が入っていないか検査する。

    見つけたら ``TableError`` を送出する。エラー値には「何が・どこで・
    どうすればよいか」を入れる（共通規約 7 章）。
    """
    for level_name in levels:
        value = row[level_name]
        if isinstance(value, str) and value.strip() in _EXCEL_ERROR_VALUES:
            raise TableError(
                f"Table の{row_number}件目、列「{level_name}」の値"
                f"「{value}」はExcelのエラー値のため階層判定に使えません。"
                "\n対処: Excel の式や参照を修正してください。"
            )


def _build_subtotal_row(
    row: dict[str, Any],
    levels: list[str],
    current: list[Any],
    topmost_idx: int,
) -> dict[str, Any]:
    """小計行の出力を作る。matched level より上は current、matched level は
    元の値、下は None。階層以外の列は元の値のまま。"""
    out_row = dict(row)
    for level_idx, level_name in enumerate(levels):
        if level_idx < topmost_idx:
            out_row[level_name] = current[level_idx]
        elif level_idx == topmost_idx:
            out_row[level_name] = row[level_name]
        else:
            out_row[level_name] = None
    return out_row


def _advance_current(row: dict[str, Any], levels: list[str], current: list[Any]) -> None:
    """明細行を見て current を進める。

    上の階層から順に、値があれば current を更新し、それより下をクリアする
    （大分類が変わったら前の中分類を持ち越さない）。値が現在の current と
    同じなら何もしない。
    """
    for level_idx, level_name in enumerate(levels):
        value = row[level_name]
        if _is_empty_value(value):
            # 空なら current を使う（更新しない）
            continue
        if _strip_value(value) == _strip_value(current[level_idx]):
            # 値があり、現在の値と同じなら何もしない
            continue
        current[level_idx] = value
        for j in range(level_idx + 1, len(current)):
            current[j] = None


def _collect_unmatched_for_row(
    row: dict[str, Any],
    levels: list[str],
    row_number: int,
    unmatched: list[int],
) -> None:
    """「計」で終わるセルが小計判定外なら unmatched に件目を入れ、警告を出す。

    同じ行は 2 度入れない。階層以外の列は見ない。
    """
    for level_name in levels:
        value = row[level_name]
        if value is None:
            continue
        stripped = str(value).strip()
        if stripped.endswith("計"):
            unmatched.append(row_number)
            logger.warning(
                "Table の%d件目、列「%s」の値「%s」が「計」で終わる"
                "のに小計と判定されませんでした（明細として出力します）。",
                row_number,
                level_name,
                value,
            )
            return  # 同じ行を 2 度入れない


def _build_detail_row(
    row: dict[str, Any],
    levels: list[str],
    current: list[Any],
) -> dict[str, Any]:
    """明細行の出力を作る。全階層を current の値で埋める（階層以外は元の値）。"""
    out_row = dict(row)
    for level_idx, level_name in enumerate(levels):
        out_row[level_name] = current[level_idx]
    return out_row


def split_hierarchy_rows(
    rows: list[dict[str, Any]],
    levels: list[str],
    *,
    subtotal_words: tuple[str, ...],
    subtotal_suffixes: tuple[str, ...],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[int]]:
    """行データを階層で分けて ``(details, subtotals, unmatched)`` を返す。

    ``Table.split_hierarchy()`` から呼ばれる内部用。``_from_normalized_rows``
    で Table へ戻すのは呼び出し側の責任。

    Args:
        rows: 元の Table の行（types 変換済み）。
        levels: 階層の列名（上から順）。
        subtotal_words: 小計と完全一致で扱う値のタプル。
        subtotal_suffixes: 小計として扱う接尾辞のタプル。

    Returns:
        ``(details, subtotals, unmatched)`` のタプル。``unmatched`` は
        「計」で終わる値があるのに小計と判定しなかった行の件目（1始まり）。

    Raises:
        TableError: 階層の列に Excel のエラー値文字列がある。
    """
    detail_rows: list[dict[str, Any]] = []
    subtotal_rows: list[dict[str, Any]] = []
    unmatched: list[int] = []
    # 各階層の現在の値。上の階層が変わったら「それより下」を None に戻す
    current: list[Any] = [None] * len(levels)

    for row_number, row in enumerate(rows, 1):
        _check_excel_errors(row, levels, row_number)

        # 行の列が全部空ならどちらにも出さない（共通規約の「全部の列が空」）
        if all(_is_empty_value(value) for value in row.values()):
            continue

        # 小計判定（current を更新する前に判定する）
        topmost_idx = _find_topmost_subtotal_level(
            row, levels, current, subtotal_words, subtotal_suffixes
        )

        if topmost_idx is not None:
            subtotal_rows.append(_build_subtotal_row(row, levels, current, topmost_idx))
            continue

        # 明細行
        _advance_current(row, levels, current)
        _collect_unmatched_for_row(row, levels, row_number, unmatched)
        detail_rows.append(_build_detail_row(row, levels, current))

    return detail_rows, subtotal_rows, unmatched


__all__ = [
    "HierarchyResult",
    "SUBTOTAL_SUFFIXES",
    "SUBTOTAL_WORDS",
    "split_hierarchy_rows",
]
