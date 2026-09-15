"""comken/toolbox/csv/transform_file.py — CSVファイルを読み、加工して同じ名前で書き戻す。

「加工が先、バックアップは成功した後にだけ作る」という骨格だけを持つ。
加工の中身（列を絞る・値を変換する等）は呼び出し側が transform で渡す。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from comken.core.files import copy_file
from comken.toolbox.csv.file import CSV

if TYPE_CHECKING:
    from collections.abc import Callable

    from comken.core.table.model import Table


def transform_csv_file(
    path: str | Path,
    transform: Callable[[Table], Table],
    *,
    backup_suffix: str = "_bak",
) -> Path:
    """CSVファイルを読み、transform(table) の結果を同じパス・同じファイル名で書き戻す。

    **transform が先、バックアップは成功した後にだけ作る。** transform が失敗
    しても（列名の設定ミス等）この順序なら元ファイルには一切手を付けていない
    ため、設定を直してそのまま同じファイルへ再実行できる（先にファイルを
    退避してから加工する順序だと、失敗するたびに直前の正常なバックアップが
    次のリトライで上書きされ、失敗を繰り返すと元データを失いかねない）。

    バックアップは拡張子の前に ``backup_suffix`` を挟んだ名前
    （例: ``応需.csv`` → ``応需_bak.csv``）で、transform 成功後の元ファイルの
    複製。``.csv`` のまま残すのは、CSV クラスが ``.csv`` 以外の拡張子を
    受け付けないため。既に同名のバックアップがあれば上書きする（直前の
    成功時点の複製なので、古い方を残す意味は無い）。自動削除はしない
    — 消すかどうかは呼び出し側が決める。

    Args:
        path: 加工したいCSVのパス。
        transform: 読み込んだ Table を受け取り、書き戻したい Table を返す関数。
        backup_suffix: バックアップファイル名に付ける接尾辞。

    Returns:
        バックアップファイルのパス。
    """
    path = Path(path)
    with CSV(path, read_only=True) as source:
        table = source.read()
    # ここで失敗すれば元ファイルは無傷のまま送出される（下のバックアップ・書き戻しに進まない）
    result = transform(table)

    backup_path = path.with_name(f"{path.stem}{backup_suffix}{path.suffix}")
    copy_file(path, backup_path)

    with CSV(path) as dest:
        dest.replace(result)
    return backup_path
