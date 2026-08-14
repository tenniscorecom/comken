r"""comken/services/salesforce_downloader/master.py — レポート管理表の列を決める。

**このファイルにあるのは「社内の取り決め」だけ。** Excel を読む・検証する・雛形を作る
仕組みは `comken.toolbox.master_table` にあり、ここは**どんな列があるか**を宣言する。

    | ID   | 概要     | Salesforce URL              | 実行方式 | 保存先              | 有効 |
    |------|----------|-----------------------------|----------|---------------------|------|
    | 1001 | 顧客一覧 | https://.../Report/00O.../  | 定期     | \\server\A\input    | 有効 |

**Salesforce のレポート ID は入力させない。** URL を貼れば `report_id_from_url()` が
取り出す。ID を人が抜き出す工程を挟むと、そこで写し間違いが起きるうえ、
「どのレポートか」を確かめるには結局 URL を開くことになる。

**ID（管理番号）は Salesforce のレポート ID ではない。** 社内で決める論理的な番号で、
同じ意味のデータを指す限り変えない。参照先の Salesforce レポートを差し替えても、
利用側の Python コード（`CUSTOMER_LIST = 1001`）は変えずに済む。
"""

from dataclasses import dataclass
from pathlib import Path

from ...exceptions import InvalidReportUrlError, SalesforceReportIdNotFoundError
from ...toolbox.master_table import MasterRow, column
from ...toolbox.salesforce import report_id_from_url

# 「実行方式」に書ける値
SCHEDULED = "定期"
ON_DEMAND = "個別"

# 記入例（雛形に入れる）。2行目は別のレポートにする——同じ URL を並べると、
# check が「同じレポートを指している」と報告してしまう
_DOMAIN = "https://example--sandbox.sandbox.my.salesforce.com/lightning/r/Report"
EXAMPLES = [
    {
        "key": 1001,
        "summary": "顧客一覧",
        "url": f"{_DOMAIN}/00O5g00000ABCDE/view",
        "schedule": SCHEDULED,
        "folder": r"\\server\案件集計\input",
        "enabled": True,
    },
    {
        "key": 1002,
        "summary": "売上実績",
        "url": f"{_DOMAIN}/00O5g00000FGHIJ/view",
        "schedule": ON_DEMAND,
        "folder": r"\\server\売上帳票\input",
        "enabled": True,
    },
]


@dataclass(frozen=True)
class ReportEntry(MasterRow):
    """レポート管理表の1行。"""

    SHEET_NAME = "管理表"

    key: int = column(
        "ID",
        unique=True,
        help="社内で決める管理番号。Salesforce のレポート ID ではありません。"
        "参照先のレポートを差し替えても、この番号は変えません",
    )
    summary: str = column(
        "概要", help="人が読んで何のレポートか分かる説明。保存するファイル名にも使われます"
    )
    url: str = column(
        "Salesforce URL",
        help="Salesforce でレポートを開いたときのアドレスを、そのまま貼り付けてください。"
        "レポート ID を抜き出す必要はありません",
    )
    schedule: str = column(
        "実行方式",
        choices=(SCHEDULED, ON_DEMAND),
        help=f"「{SCHEDULED}」は毎日決まった時刻にまとめて取ります。"
        f"「{ON_DEMAND}」は、使うプログラムから呼ばれたときだけ取ります",
    )
    folder: Path = column(
        "保存先",
        help="落としたファイルを置くフォルダ。フォルダが無いとエラーになります"
        "（打ち間違いに気づけるよう、勝手には作りません）",
    )
    enabled: bool = column(
        "有効",
        default=True,
        help="使わなくなったら「無効」にしてください。行は消さないでください"
        "（過去の履歴と対応が取れなくなります）",
    )

    @property
    def report_id(self) -> str:
        """URL から取り出した Salesforce のレポート ID。

        **行番号ではなく管理番号で示す。** 空行を飛ばして読むので行番号はズレうるが、
        管理番号なら管理表を検索して一発で見つかる。

        Raises:
            InvalidReportUrlError: URL からレポート ID を取り出せない場合。
        """
        try:
            return report_id_from_url(self.url)
        except SalesforceReportIdNotFoundError as e:
            raise InvalidReportUrlError(self.key, self.url, str(e)) from e

    @property
    def is_scheduled(self) -> bool:
        """定期取得の対象か。"""
        return self.schedule == SCHEDULED


def load_master(path: str | Path | None = None) -> dict[int, ReportEntry]:
    """管理表を読んで、管理番号をキーにした辞書を返す。

    Args:
        path: 管理表（Excel）のパス。

    Returns:
        {管理番号: ReportEntry}。管理表に並んでいる順を保つ。
    """
    entries = {}
    for entry in ReportEntry.load(path):
        entry.report_id  # noqa: B018 — URL が壊れていれば、ここで読み込みごと止める
        entries[entry.key] = entry
    return entries


def shared_report_ids(entries: dict[int, ReportEntry]) -> dict[str, list[int]]:
    """同じ Salesforce レポートを指している管理番号を返す。

    **同じレポートを複数のプロジェクトが別々の管理番号で使っている**ことが分かる。
    エラーにはしない——意図してそうしている場合（保存先を分けたい等）もあるため、
    気づけるようにするだけにする。

    Returns:
        {Salesforce のレポート ID: [管理番号, ...]}。2つ以上のものだけ。
    """
    by_report_id: dict[str, list[int]] = {}
    for entry in entries.values():
        by_report_id.setdefault(entry.report_id, []).append(entry.key)
    return {report_id: keys for report_id, keys in by_report_id.items() if len(keys) > 1}
