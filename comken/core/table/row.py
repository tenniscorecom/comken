"""comken/core/table/row.py — 表の「行」を表す型の名前。"""

from typing import Any

# Table は表全体（pandas でいう DataFrame）、Row は表の 1 行（pandas でいう Series）。
# 値は列ごとに ``types=`` で変換できるため ``Any``。CSV を読んだだけなら値は文字列。
# 戻り値の注釈を ``dict[str, Any]`` と書き散らさず、行を指すときはこの名前を使う。
Row = dict[str, Any]
