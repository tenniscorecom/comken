"""comken/services/csv_column_reducer/file_ops.py — CSVファイル単位での列削減（バックアップ付き）。

ファイルの読み書き・バックアップの骨格は comken.toolbox.csv.transform_csv_file()
が汎用で持っている。ここは応需固有の加工（reduce_ouju_csv）をそこへ渡すだけ。
"""

from __future__ import annotations

from pathlib import Path

from comken.services.csv_column_reducer.ouju_role import reduce_ouju_csv
from comken.toolbox.csv import transform_csv_file


def reduce_ouju_csv_file(
    path: str | Path,
    *,
    columns: list[str] | None = None,
    backup_suffix: str = "_bak",
) -> Path:
    """CSVファイルを読み、旧ロール列だけに絞って同じパス・同じファイル名で書き戻す。

    処理の骨格（列削減が先、バックアップは成功後にだけ作る等）は
    comken.toolbox.csv.transform_csv_file() の docstring を参照。

    Args:
        path: 応需からダウンロードしたCSVのパス。
        columns: 残す列名を上書きしたいときに指定する。省略時は
            ouju_role.OLD_ROLE_COLUMNS（旧ロール相当）を使う。
        backup_suffix: バックアップファイル名に付ける接尾辞。

    Returns:
        バックアップファイルのパス。
    """
    return transform_csv_file(
        path,
        lambda table: reduce_ouju_csv(table, columns=columns),
        backup_suffix=backup_suffix,
    )
