"""comken/core/types.py — 表やセルを扱う API の注釈に使う、共通の型の名前。

注釈に使うときは、ここから 1 行で import する（``from comken.core.types import Row``）。
複数のモジュールの引数や戻り値に出てくる型だけを置く。1 つのモジュールの中でしか使わない型は、
そのモジュールに置く。
"""

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

# 表の 1 行（pandas でいう Series）。表全体は Table（DataFrame）。値は列ごとに ``types=`` で
# 変換できるため ``Any``。CSV を読んだだけなら、値は文字列
Row = dict[str, Any]

# セルに書き込める値（CSV・Excel 共通）
Value = str | int | float | bool | datetime

# ``types=`` に渡す「列名 → 変換する関数」の表
TypeMap = Mapping[str, Callable[[Any], Any]]
