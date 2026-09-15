"""comken/services/csv_column_reducer/__init__.py — 応需CSVの新ロール→旧ロール列削減。

新ロールでは列数が255を超えてAccessへ取り込めないため、既定では旧ロール
相当の列だけを残す。列名ゆれの吸収を含む列選択そのものは Table.select(aliases=...)
（comken.core.table.model.Table）、ファイル単位の読み書き・バックアップの骨格は
comken.toolbox.csv.transform_csv_file() がそれぞれ汎用で持っている。
このパッケージは応需固有の値（列リスト・リネーム対応表）だけを持ち、
ファイルをまとめて処理したいときは両者を組み合わせて使う。

    from comken.services.csv_column_reducer import reduce_ouju_csv
    from comken.toolbox.csv import transform_csv_file

    transform_csv_file("応需.csv", reduce_ouju_csv)  # 旧ロール列だけに絞って同じ名前で書き戻す

    # 残す列を上書きしたいときは lambda で columns を渡す
    transform_csv_file("応需.csv", lambda table: reduce_ouju_csv(table, columns=["氏名"]))

応需CSV向けの既定値は ouju_role.py（Table 単位）を参照。ダウンロード自体は
このパッケージの範囲外（利用プロジェクト側で行う）。

**このファイルが持つもの:**
- 応需CSV向けの既定の列リスト・リネーム対応表（雛形。実データは利用側で埋める）
- Table 単位の削減（reduce_ouju_csv）

**ここに書かないもの:**
- 列選択そのもの（列名ゆれの吸収を含む） → comken.core.table.model.Table.select()
- ファイルの読み書き・バックアップの骨格 → comken.toolbox.csv.transform_csv_file()
- Access への取り込み自体 → 利用プロジェクト
- 応需からのCSVダウンロード自体 → 利用プロジェクト
"""

from comken.services.csv_column_reducer.ouju_role import (
    OLD_ROLE_ALIASES,
    OLD_ROLE_COLUMNS,
    reduce_ouju_csv,
)

__all__ = [
    "reduce_ouju_csv",
    "OLD_ROLE_COLUMNS",
    "OLD_ROLE_ALIASES",
]
