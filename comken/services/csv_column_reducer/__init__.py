"""comken/services/csv_column_reducer/__init__.py — 列名ゆれを吸収した列削減。

CSV の列を「欲しい列名のリスト」だけに絞る。列名がリネームされていても
対応表（aliases）で吸収できる。応需CSVの新ロール対応（列数が255を超えて
Access へ取り込めない問題）が最初の用途だが、汎用の核（reduce_columns）は
応需固有の知識を持たないため、他システムでも同じ形で使い回せる。

    from comken.services.csv_column_reducer import reduce_columns

    reduced = reduce_columns(table, ["顧客番号", "氏名"], aliases={"顧客番号": "顧客ID"})

応需CSV向けの既定値付きラッパーは ouju_role.py（Table 単位）・
file_ops.py（ファイル単位、バックアップ付き）を参照。ダウンロード自体は
このパッケージの範囲外（利用プロジェクト側で行う）。

**このファイルが持つもの:**
- 列名ゆれを吸収した列選択の核（reduce_columns）
- 応需CSV向けの既定の列リスト・リネーム対応表（雛形。実データは利用側で埋める）

**ここに書かないもの:**
- Access への取り込み自体 → 利用プロジェクト
- 応需からのCSVダウンロード自体 → 利用プロジェクト
"""

from comken.services.csv_column_reducer.file_ops import reduce_ouju_csv_file
from comken.services.csv_column_reducer.ouju_role import (
    OLD_ROLE_ALIASES,
    OLD_ROLE_COLUMNS,
    reduce_ouju_csv,
)
from comken.services.csv_column_reducer.reducer import reduce_columns

__all__ = [
    "reduce_columns",
    "reduce_ouju_csv",
    "reduce_ouju_csv_file",
    "OLD_ROLE_COLUMNS",
    "OLD_ROLE_ALIASES",
]
