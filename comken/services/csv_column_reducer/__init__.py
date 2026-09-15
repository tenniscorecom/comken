"""comken/services/csv_column_reducer/__init__.py — 応需CSVの新ロール→旧ロール列削減。

新ロールでは列数が255を超えてAccessへ取り込めないため、既定では旧ロール
相当の列だけを残す。列名ゆれの吸収を含む列選択そのものは Table.select(aliases=...)
が汎用で持っている（comken.core.table.model.Table）。このパッケージは
応需固有の値（列リスト・リネーム対応表）と、ファイル単位の入出力だけを持つ。

    from comken.services.csv_column_reducer import reduce_ouju_csv_file

    reduce_ouju_csv_file("応需.csv")  # 旧ロール列だけに絞って同じ名前で書き戻す

応需CSV向けの既定値は ouju_role.py（Table 単位）を参照。ダウンロード自体は
このパッケージの範囲外（利用プロジェクト側で行う）。

**このファイルが持つもの:**
- 応需CSV向けの既定の列リスト・リネーム対応表（雛形。実データは利用側で埋める）
- ファイル単位の削減（バックアップ付き）

**ここに書かないもの:**
- 列選択そのもの（列名ゆれの吸収を含む） → comken.core.table.model.Table.select()
- ファイルの読み書き・バックアップの骨格 → comken.toolbox.csv.transform_csv_file()
- Access への取り込み自体 → 利用プロジェクト
- 応需からのCSVダウンロード自体 → 利用プロジェクト
"""

from comken.services.csv_column_reducer.file_ops import reduce_ouju_csv_file
from comken.services.csv_column_reducer.ouju_role import (
    OLD_ROLE_ALIASES,
    OLD_ROLE_COLUMNS,
    reduce_ouju_csv,
)

__all__ = [
    "reduce_ouju_csv",
    "reduce_ouju_csv_file",
    "OLD_ROLE_COLUMNS",
    "OLD_ROLE_ALIASES",
]
