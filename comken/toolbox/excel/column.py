"""comken/toolbox/excel/column.py — 列番号 ⇄ 列記号の変換。

``column_letter()`` は ``col_to_num()``（``comken.core.columns``）の逆変換。
1始まりで ``1 → "A"``、``26 → "Z"``、``27 → "AA"``、``702 → "ZZ"``、
``703 → "AAA"`` の形に対応する。

``get_column_letter`` の薄い別名 (``from openpyxl.utils import
get_column_letter as _gcl``) だと openpyxl に直接依存することになるため、
comken の公開窓口に **comken 自身の純粋な実装** として置く。値は openpyxl
のそれと同じ（1始まり、A1 形式と同じ並び）なので、置き換えても結果は変わらない。
"""


def column_letter(index: int) -> str:
    """1始まりの列番号を Excel の列記号に変換する（``1 → "A"``）。

    ``col_to_num()`` の逆関数。Excel の列は A, B, ..., Z, AA, AB, ..., AZ, BA,
    ... と続き、これは **1始まり 26進数**（桁は A〜Z）で表せる。
    1始まりなので ``Z`` の次は ``AA``（=0,0 ではない点だけ注意）。

    Args:
        index: 1始まりの列番号。

    Returns:
        ``"A"`` 〜 ``"ZZZ"`` の列記号。

    Raises:
        ValueError: ``index`` が 1 未満の場合。
    """
    if index < 1:
        raise ValueError(
            f"列番号は1以上である必要があります（実際: {index}）。"
            "Excel の列は A 列（=1）から始まります。"
        )
    letters: list[str] = []
    remaining = index
    while remaining > 0:
        # 1始まりを 0始まりの 26 進数になおす（A=0, ..., Z=25）。
        # 「Z の次が AA」になるように、毎回 -1 してから mod 26 する。
        remaining, remainder = divmod(remaining - 1, 26)
        letters.append(chr(ord("A") + remainder))
    return "".join(reversed(letters))


__all__ = ["column_letter"]
