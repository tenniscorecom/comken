"""comken/services/salesforce_downloader/sheets/group_settings.py — グループ設定シート。

**`sheets/` には、ワークブック・CSVの「1枚（1ファイル）」ごとに、そこにある列と
意味を宣言するモジュールを集めている**（`master.py` = レポート管理表シート、
`schedule.py` = スケジュールシート、`history.py` = 履歴CSV、
`group_settings.py` = このファイル）。

**このシートはレポート管理表と同じブック内の別シート**として配置する
（`schedule.py` の `load_schedule()` が `MASTER_PATH` を使い回しているのと同じ
設計）。1行に「グループ名」と「ベースパス」を書き、管理表の `ReportEntry.group`
から出力先を引くときに使う。ベースパスの下の第2階層に「担当者」、第3階層に
「概要」を連結するのが `report_folder()` の組み立てルールで、Excel の
数式 (VLOOKUP 等) ではなく Python 側で組み立てる。

レポート管理表本体とは別ファイルにしない理由は `schedule.py` と同じ——人が
ブックを1つだけ開けば管理表と設定の両方を確認できるようにするため。
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from comken.core.timer import measure
from comken.services.salesforce_downloader.report_master import MasterRow, column

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class GroupSetting(MasterRow):
    """「設定」シートの1行。出力先の起点（ベースパス）をグループに紐付ける。

    ``unique=True`` の ``group`` 列で、**同じグループ名が2行に書かれていたら
    エラーにする**（ベースパスが2つあると、どちらに従うか決められないため）。
    """

    SHEET_NAME = "設定"
    # ``PATH`` クラス変数は設定しない。``ReportEntry`` と同じく ``load_group_settings()``
    # の引数または ``MASTER_PATH`` で指定する

    group: str = column(
        "グループ",
        unique=True,
        help="レポート管理表の「グループ」列と一致させる社内のグループ名・部署名。"
        "同じ名前は1行しか登録できません",
    )
    base_path: Path = column(
        "ベースURL",
        help="このグループの出力先の起点パス（例: \\\\server\\share\\営業本部）。"
        "出力ファイルは「ベースパス / 担当者 / 概要 /」の下に置きます",
    )


@measure
def load_group_settings(path: str | Path | None = None) -> dict[str, Path]:
    """設定シートを読んで、{グループ名: ベースパス} の辞書を返す。

    ``load_schedule()`` と同じパターンで、``path=None`` のときは
    ``MASTER_PATH`` を使う（設定シートはレポート管理表と同じブックにあるため、
    別パスを渡す必要は基本的に無い）。

    Args:
        path: 設定シートを含む Excel のパス。``None`` のときは ``MASTER_PATH``。

    Returns:
        ``{グループ名: ベースパス}``。グループ名は「設定」シートに書かれた順を保つ。
    """
    if path is None:
        from comken.services.salesforce_downloader.paths import MASTER_PATH

        path = MASTER_PATH
    source = Path(path)
    logger.debug("グループ設定読込開始: path=%s", source)
    settings = {setting.group: setting.base_path for setting in GroupSetting.load(source)}
    logger.debug("グループ設定読込完了: path=%s, 件数=%d", source, len(settings))
    return settings
