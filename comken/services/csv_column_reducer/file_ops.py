"""comken/services/csv_column_reducer/file_ops.py — CSVファイル単位での列削減（バックアップ付き）。

Table を受け取る reduce_ouju_csv() はファイルを触らない。ここではその1段上として、
ダウンロードしたCSVファイルをそのまま読み、列を削減して同じファイル名で書き戻す
（Access側の取り込み設定などをファイル名変更に合わせて直さなくてよいようにするため）。
"""

from __future__ import annotations

import logging
from pathlib import Path

from comken.core.files import move_file
from comken.services.csv_column_reducer.ouju_role import reduce_ouju_csv
from comken.toolbox.csv import CSV

logger = logging.getLogger(__name__)


def reduce_ouju_csv_file(
    path: str | Path,
    *,
    columns: list[str] | None = None,
    backup_suffix: str = "_bak",
) -> Path:
    """CSVファイルを読み、旧ロール列だけに絞って同じパス・同じファイル名で書き戻す。

    加工前のファイルは拡張子の前に ``backup_suffix`` を挟んだ名前
    （例: ``応需.csv`` → ``応需.bak.csv``）へリネームしてから書き直す
    （処理前の状態を残す。``.csv`` のまま残すのは、CSV クラスが ``.csv``
    以外の拡張子を受け付けないため。自動削除はしない — 消すかどうかは
    呼び出し側が決める）。同名のバックアップが既にあれば上書きする
    （move_file の挙動どおり）。

    Args:
        path: 応需からダウンロードしたCSVのパス。
        columns: 残す列名を上書きしたいときに指定する。省略時は
            ouju_role.OLD_ROLE_COLUMNS（旧ロール相当）を使う。
        backup_suffix: バックアップファイル名に付ける接尾辞。

    Returns:
        リネーム後のバックアップファイルのパス。
    """
    path = Path(path)
    backup_path = path.with_name(f"{path.stem}{backup_suffix}{path.suffix}")
    move_file(path, backup_path)
    logger.info("加工前のCSVをバックアップへ退避しました: %s", backup_path)

    with CSV(backup_path, read_only=True) as source:
        table = source.read()
    reduced = reduce_ouju_csv(table, columns=columns)

    with CSV(path) as dest:
        dest.replace(reduced)
    logger.info(
        "列を削減したCSVを書き出しました: %s (%d列 → %d列)",
        path,
        len(table.columns),
        len(reduced.columns),
    )
    return backup_path
