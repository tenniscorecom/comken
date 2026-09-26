"""comken/services/csv_column_reducer.py — 応需CSVの新ロール→旧ロール列削減。

応需システムを「新ロール」で使うと、ダウンロードされるCSVの列数が255を超えて
Access へ取り込めなくなる。既定では旧ロール相当の列だけを残して回避する。

列名ゆれの吸収を含む列選択そのものは Table.select(aliases=...)
（comken.core.table.model.Table）が汎用で持っている。ファイルの読み書き・
バックアップは、応需固有のこの使い方に限って ここで直接扱う
（サービス固有の使い方なので、toolbox 側を汎用化する必要はないと判断した）。

    from comken.services.csv_column_reducer import reduce_ouju_csv_file

    reduce_ouju_csv_file("応需.csv")  # 旧ロール列だけに絞って同じ名前で書き戻す

**bat から呼んで、同じフォルダの CSV を全部変換する**（元の新ロールのファイルは ``_bak`` に残る）:

    @echo off
    pushd "%~dp0"
    python -m comken.services.csv_column_reducer

bat に CSV ファイルやフォルダを**ドラッグ＆ドロップ**すると、落としたものだけが対象になる
（何も落とさずに実行すれば、bat のあるフォルダ）。すでに旧ロールの列だけになっているファイルと、
``_bak`` のファイルは飛ばす（2回実行しても、新ロールのバックアップは上書きされない）。

列名・リネーム対応表は環境依存の実データなので、ここはダミーのまま
（利用プロジェクト側で実際の値へ書き換える前提）。

**このファイルが持つもの:**
- 応需CSV向けの既定の列リスト・リネーム対応表（雛形。実データは利用側で埋める）
- Table 単位の削減（reduce_ouju_csv）・ファイル単位の削減（reduce_ouju_csv_file）・
  フォルダ単位の削減（reduce_ouju_csv_folder。bat からは ``python -m`` で呼ぶ）

**ここに書かないもの:**
- 列選択そのもの（列名ゆれの吸収を含む） → comken.core.table.model.Table.select()
- Access への取り込み自体 → 利用プロジェクト
- 応需からのCSVダウンロード自体 → 利用プロジェクト
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from comken.core.files import copy_file
from comken.core.table.model import Table
from comken.core.timer import measure
from comken.exceptions import ComkenError, CSVError
from comken.toolbox.csv import CSV

logger = logging.getLogger(__name__)

# 旧ロールで残す列名（この並び順で出力される）。
# TODO: 実際の旧ロールの列名に書き換える
OLD_ROLE_COLUMNS: list[str] = []

# 新ロールでリネームされた列のうち、先頭の*有無では説明できないものだけ
# {旧ロールでの列名: 新ロールでの実際の列名}。
# 先頭の*有無だけが違う列（新ロールの必須マーク等）は _resolve_asterisk_aliases()
# が自動で吸収するため、ここに書かなくてよい
# TODO: 実際にリネームされた列（*以外の理由によるもの）があれば追記する
OLD_ROLE_ALIASES: dict[str, str] = {}


def reduce_ouju_csv(table: Table, *, columns: list[str] | None = None) -> Table:
    """応需CSVの Table を、既定では旧ロール列だけに絞って返す。

    columns を渡すと、既定の OLD_ROLE_COLUMNS の代わりにそちらを使う
    （新ロールへ完全移行した後や、他システム向けに必要な列だけ残したいときに使う）。

    先頭の*有無だけが違う列は自動で吸収し、結果の列名は常に旧ロール側
    （columns / OLD_ROLE_COLUMNS で指定した名前）に揃える。それ以外の
    リネームは OLD_ROLE_ALIASES を使う（自動判定より OLD_ROLE_ALIASES を優先する）。
    """
    wanted = columns if columns is not None else OLD_ROLE_COLUMNS
    aliases = {**_resolve_asterisk_aliases(table.columns, wanted), **OLD_ROLE_ALIASES}
    return table.select(*wanted, aliases=aliases)


@measure
def reduce_ouju_csv_file(
    path: str | Path,
    *,
    columns: list[str] | None = None,
    backup_suffix: str = "_bak",
) -> Path:
    """CSVファイルを読み、旧ロール列だけに絞って同じパス・同じファイル名で書き戻す。

    **削減が先、バックアップは成功した後にだけ作る。** OLD_ROLE_COLUMNS の
    設定ミス等で削減が失敗しても、この順序なら元ファイルには一切手を付けて
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
            OLD_ROLE_COLUMNS（旧ロール相当）を使う。
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

    with CSV(path) as dest:
        dest.replace(reduced)
    return backup_path


@measure
def reduce_ouju_csv_files(
    paths: list[Path],
    *,
    columns: list[str] | None = None,
    backup_suffix: str = "_bak",
) -> list[Path]:
    """指定した CSV を、旧ロールの列だけに絞る（``reduce_ouju_csv_file`` を順に呼ぶ）。

    次のファイルは飛ばす（ログに出す）:

    - ``backup_suffix`` で終わるファイル（バックアップそのもの）
    - **すでに旧ロールの列だけになっているファイル。** 飛ばさないと、2回目の実行で
      新ロールのバックアップが、旧ロールに絞ったファイルで上書きされて失われる。
      「バックアップがあるか」では判定しない（同じ名前で新しくダウンロードした CSV が
      飛ばされてしまうため）

    1ファイルが失敗（欲しい列が無い等）しても、残りは処理する。失敗したファイルは
    最後にまとめて ``CSVError`` で知らせる（bat が終了コードで気づけるように）。

    Returns:
        変換したファイルのバックアップのパス。
    """
    wanted = columns if columns is not None else OLD_ROLE_COLUMNS
    backups: list[Path] = []
    failures: list[str] = []
    for path in paths:
        if path.stem.endswith(backup_suffix):
            logger.info("バックアップのファイルなので飛ばします: %s", path.name)
            continue
        try:
            with CSV(path, read_only=True) as source:
                if source.read().columns == wanted:
                    logger.info("すでに旧ロールの列だけなので飛ばします: %s", path.name)
                    continue
            backups.append(reduce_ouju_csv_file(path, columns=columns, backup_suffix=backup_suffix))
        except ComkenError as error:
            logger.error("変換できませんでした: %s（%s）", path.name, error)
            failures.append(path.name)
        else:
            logger.info("旧ロールの列に変換しました: %s", path.name)
    if failures:
        raise CSVError(
            f"{len(failures)} 件の CSV を変換できませんでした: {', '.join(failures)}\n"
            "上のログで、それぞれの原因（欲しい列が無い等）を確認してください。"
            "変換できなかったファイルは、元のまま変更していません。"
        )
    return backups


@measure
def reduce_ouju_csv_folder(
    folder: str | Path,
    *,
    columns: list[str] | None = None,
    backup_suffix: str = "_bak",
) -> list[Path]:
    """フォルダ内の ``*.csv`` を、すべて旧ロールの列だけに絞る。

    飛ばす条件・失敗したときの扱いは ``reduce_ouju_csv_files`` と同じ。
    """
    csv_files = sorted(path for path in Path(folder).glob("*.csv") if path.is_file())
    return reduce_ouju_csv_files(csv_files, columns=columns, backup_suffix=backup_suffix)


def main(argv: list[str] | None = None) -> None:
    """``python -m comken.services.csv_column_reducer [ファイルやフォルダ ...]``。

    引数はファイルでもフォルダでもよい（bat へのドラッグ＆ドロップで渡される）。
    フォルダは中の ``*.csv`` を対象にする。何も渡さなければ現在のフォルダを対象にする。
    """
    parser = argparse.ArgumentParser(description="CSV を旧ロールの列だけにする")
    parser.add_argument(
        "paths", nargs="*", type=Path, help="対象のファイルやフォルダ（省略時は現在のフォルダ）"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    targets: list[Path] = []
    for path in args.paths or [Path()]:
        if path.is_dir():
            targets += sorted(p for p in path.glob("*.csv") if p.is_file())
        else:
            targets.append(path)
    try:
        backups = reduce_ouju_csv_files(targets)
    except CSVError as error:
        logger.error("%s", error)
        raise SystemExit(1) from error
    logger.info("完了: %d 件を変換しました", len(backups))


def _resolve_asterisk_aliases(
    table_columns: list[str], wanted_columns: list[str]
) -> dict[str, str]:
    """欲しい列名のうち、先頭の*の有無だけが違う実列名を自動で対応付ける。

    新ロールでは必須項目に*が付く等、列によって*が増えたり消えたりする
    （一律の付け外しではない）ため、先頭の*を無視して同じ列とみなす。
    完全一致する列はここでは対応表に入れない（select() がそのまま解決できるため）。
    """
    by_stripped = {name.removeprefix("*"): name for name in table_columns}
    aliases = {}
    for wanted in wanted_columns:
        if wanted in table_columns:
            continue
        actual = by_stripped.get(wanted.removeprefix("*"))
        if actual is not None:
            aliases[wanted] = actual
    return aliases


if __name__ == "__main__":
    main()
