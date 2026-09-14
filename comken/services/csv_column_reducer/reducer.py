"""comken/services/csv_column_reducer/reducer.py — 列名ゆれを吸収した列選択。

``Table.select()`` は列名の完全一致だけを扱う。ここでは「欲しい列名」と
「実際に Table 側にある列名」がリネームでずれているケースを、呼び出し側が
明示した対応表（aliases）で吸収してから select する。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from comken.core.table.model import Table


def reduce_columns(
    table: Table,
    columns: Sequence[str],
    *,
    aliases: Mapping[str, str] | None = None,
) -> Table:
    """columns（欲しい列名）だけを残した Table を返す。

    aliases に ``{欲しい列名: 実際に table にある列名}`` を渡すと、列名が
    変わっていてもそちらから値を拾う。結果の列名は常に columns 側（欲しい
    名前）に揃う。aliases に無い列は、table 側にも同じ名前でそのまま
    存在する前提で選ぶ。

        # 「顧客番号」が新ロールでは「顧客ID」にリネームされている場合
        reduce_columns(table, ["顧客番号", "氏名"], aliases={"顧客番号": "顧客ID"})

    欲しい列が table に無い場合は ``Table.select()`` と同じ
    ``TableColumnNotFoundError`` になる（サイレントに欠落させない）。
    """
    aliases = aliases or {}
    actual_names = [aliases.get(wanted, wanted) for wanted in columns]
    selected = table.select(*actual_names)
    renamed_rows = [
        {wanted: row[actual] for wanted, actual in zip(columns, actual_names, strict=True)}
        for row in selected.to_rows()
    ]
    renamed_types = {
        wanted: selected.types[actual]
        for wanted, actual in zip(columns, actual_names, strict=True)
        if actual in selected.types
    }
    return Table(list(columns), renamed_rows, types=renamed_types)
