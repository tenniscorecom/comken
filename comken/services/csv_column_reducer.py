"""comken/services/csv_column_reducer.py — 応需CSVの新ロール→旧ロール列削減。

応需システムを「新ロール」で使うと、ダウンロードされるCSVの列数が255を超えて
Access へ取り込めなくなる。既定では旧ロール相当の列だけを残して回避する。

列名ゆれの吸収を含む列選択そのものは Table.select(aliases=...)
（comken.core.table.model.Table）、ファイル単位の読み書き・バックアップの骨格は
comken.toolbox.csv.transform_csv_file() がそれぞれ汎用で持っている。
このファイルは応需固有の値（列リスト・リネーム対応表）だけを持ち、
ファイルをまとめて処理したいときは両者を組み合わせて使う。

    from comken.services.csv_column_reducer import reduce_ouju_csv
    from comken.toolbox.csv import transform_csv_file

    transform_csv_file("応需.csv", reduce_ouju_csv)  # 旧ロール列だけに絞って同じ名前で書き戻す

    # 残す列を上書きしたいときは lambda で columns を渡す
    transform_csv_file("応需.csv", lambda table: reduce_ouju_csv(table, columns=["氏名"]))

列名・リネーム対応表は環境依存の実データなので、ここはダミーのまま
（利用プロジェクト側で実際の値へ書き換える前提）。

**このファイルが持つもの:**
- 応需CSV向けの既定の列リスト・リネーム対応表（雛形。実データは利用側で埋める）
- Table 単位の削減（reduce_ouju_csv）

**ここに書かないもの:**
- 列選択そのもの（列名ゆれの吸収を含む） → comken.core.table.model.Table.select()
- ファイルの読み書き・バックアップの骨格 → comken.toolbox.csv.transform_csv_file()
- Access への取り込み自体 → 利用プロジェクト
- 応需からのCSVダウンロード自体 → 利用プロジェクト
"""

from __future__ import annotations

from comken.core.table.model import Table

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
