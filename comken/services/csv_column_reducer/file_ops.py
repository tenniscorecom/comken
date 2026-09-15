"""comken/services/csv_column_reducer/file_ops.py — CSVファイル単位での列削減（バックアップ付き）。

Table を受け取る reduce_ouju_csv() はファイルを触らない。ここではその1段上として、
ダウンロードしたCSVファイルをそのまま読み、列を削減して同じファイル名で書き戻す
（Access側の取り込み設定などをファイル名変更に合わせて直さなくてよいようにするため）。
"""

from __future__ import annotations

import logging
from pathlib import Path

from comken.core.files import copy_file
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

    **列削減が先、バックアップは削減に成功した後にだけ作る。** OLD_ROLE_COLUMNS
    の設定ミス等で削減が失敗しても、この順序なら元ファイルには一切手を付けて
    いないため、設定を直してそのまま同じファイルへ再実行できる（先にファイルを
    退避してから削減する順序だと、失敗するたびに直前の正常なバックアップが
    次のリトライで上書きされ、失敗を繰り返すと元データを失いかねない）。

    バックアップは拡張子の前に ``backup_suffix`` を挟んだ名前
    （例: ``応需.csv`` → ``応需_bak.csv``）で、削減成功後の元ファイルの複製。
    ``.csv`` のまま残すのは、CSV クラスが ``.csv`` 以外の拡張子を受け付けない
    ため。既に同名のバックアップがあれば上書きする（直前の成功時点の複製なので、
    古い方を残す意味は無い）。自動削除はしない — 消すかどうかは呼び出し側が決める。

    Args:
        path: 応需からダウンロードしたCSVのパス。
        columns: 残す列名を上書きしたいときに指定する。省略時は
            ouju_role.OLD_ROLE_COLUMNS（旧ロール相当）を使う。
        backup_suffix: バックアップファイル名に付ける接尾辞。

    Returns:
        バックアップファイルのパス。
    """
    path = Path(path)
    with CSV(path, read_only=True) as source:
        table = source.read()
    # ここで失敗すれば元ファイルは無傷のまま送出される（下のバックアップ・書き戻しに進まない）
    reduced = reduce_ouju_csv(table, columns=columns)

    backup_path = path.with_name(f"{path.stem}{backup_suffix}{path.suffix}")
    copy_file(path, backup_path)
    logger.info("加工前のCSVをバックアップへ複製しました: %s", backup_path)

    with CSV(path) as dest:
        dest.replace(reduced)
    logger.info(
        "列を削減したCSVを書き出しました: %s (%d列 → %d列)",
        path,
        len(table.columns),
        len(reduced.columns),
    )
    return backup_path
