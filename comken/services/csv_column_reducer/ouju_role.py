"""comken/services/csv_column_reducer/ouju_role.py — 応需CSVの新ロール→旧ロール列削減（雛形）。

応需システムを「新ロール」で使うと、ダウンロードされるCSVの列数が255を超えて
Access へ取り込めなくなる。既定では旧ロール相当の列だけを残して回避する。

列名・リネーム対応表は環境依存の実データなので、ここはダミーのまま
（利用プロジェクト側で実際の値へ書き換える前提）。
"""

from __future__ import annotations

from comken.core.table.model import Table
from comken.services.csv_column_reducer.reducer import reduce_columns

# 旧ロールで残す列名（この並び順で出力される）。
# TODO: 実際の旧ロールの列名に書き換える
OLD_ROLE_COLUMNS: list[str] = []

# 新ロールでリネームされた列だけ {旧ロールでの列名: 新ロールでの実際の列名}。
# リネームされていない列はここに書かなくてよい（table 側にも同名で存在する前提で選ばれる）
# TODO: 実際にリネームされた列を追記する
OLD_ROLE_ALIASES: dict[str, str] = {}


def reduce_ouju_csv(table: Table, *, columns: list[str] | None = None) -> Table:
    """応需CSVの Table を、既定では旧ロール列だけに絞って返す。

    columns を渡すと、既定の OLD_ROLE_COLUMNS の代わりにそちらを使う
    （新ロールへ完全移行した後や、他システム向けに必要な列だけ残したいときに使う）。
    リネーム対応表は常に OLD_ROLE_ALIASES を使う
    （columns を差し替えても、リネームの吸収自体は変わらないため）。
    """
    wanted = columns if columns is not None else OLD_ROLE_COLUMNS
    return reduce_columns(table, wanted, aliases=OLD_ROLE_ALIASES)
