r"""comken/services/salesforce_downloader/master.py — 管理表（Excel）の読み取り。

**設定の正は Excel。** 非エンジニアが自分で編集するため、内部 DB は持たない。
呼ばれるたびに読み直す（数百行の Excel なので、貯め込むより毎回読む方が単純で、
編集した内容がすぐ効く）。

    | ID   | 概要     | Salesforce URL              | 実行方式 | 保存先              | 有効 |
    |------|----------|-----------------------------|----------|---------------------|------|
    | 1001 | 顧客一覧 | https://.../Report/00O.../  | 定期     | \\server\A\input    | 有効 |

**Salesforce のレポート ID は入力させない。** URL を貼れば
`report_id_from_url()` が取り出す。ID を人が抜き出す工程を挟むと、そこで写し間違いが
起きるうえ、「どのレポートか」を確かめるには結局 URL を開くことになる。

**ID（管理番号）は Salesforce のレポート ID ではない。** 社内で決める論理的な番号で、
同じ意味のデータを指す限り変えない。参照先の Salesforce レポートを差し替えても、
利用側の Python コード（`CUSTOMER_LIST = 1001`）は変えずに済む。
"""

from dataclasses import dataclass
from pathlib import Path

from ...exceptions import (
    DuplicateReportKeyError,
    InvalidReportEntryError,
    SalesforceReportIdNotFoundError,
)
from ...toolbox.excel import ExcelReader
from ...toolbox.salesforce import report_id_from_url

# 管理表のシート名と列名。実物の見出しと合わせる
SHEET_NAME = "管理表"
KEY_COLUMN = "ID"
SUMMARY_COLUMN = "概要"
URL_COLUMN = "Salesforce URL"
SCHEDULE_COLUMN = "実行方式"
FOLDER_COLUMN = "保存先"
ENABLED_COLUMN = "有効"

# 「実行方式」に書ける値
SCHEDULED = "定期"
ON_DEMAND = "個別"
SCHEDULES = (SCHEDULED, ON_DEMAND)

# 「有効」に書ける値（左が有効）
ENABLED_VALUES = ("有効", "有効化", "○", "o", "yes", "true", "1")

# 見出し行を除いた1行目が Excel の何行目か（見出しが1行目のため）
_FIRST_DATA_ROW = 2


@dataclass(frozen=True)
class ReportEntry:
    """管理表の1行。

    Attributes:
        key: 管理番号（社内で決める論理 ID。Salesforce のレポート ID ではない）。
        summary: 人が読んで何のレポートか分かる説明。ファイル名にも使う。
        url: Salesforce でレポートを開いたときのアドレス。
        report_id: url から取り出した Salesforce のレポート ID。
        schedule: "定期" か "個別"。
        folder: 保存先のフォルダ。
        enabled: 有効なら True。
    """

    key: int
    summary: str
    url: str
    report_id: str
    schedule: str
    folder: Path
    enabled: bool

    @property
    def is_scheduled(self) -> bool:
        """定期取得の対象か。"""
        return self.schedule == SCHEDULED


def load_master(path: str | Path) -> dict[int, ReportEntry]:
    """管理表を読んで、管理番号をキーにした辞書を返す。

    Args:
        path: 管理表（Excel）のパス。

    Returns:
        {管理番号: ReportEntry}。管理表に並んでいる順を保つ。

    Raises:
        DuplicateReportKeyError: 同じ管理番号が2つ以上ある場合。
        InvalidReportEntryError: 行の書き方が正しくない場合。
    """
    path = Path(path)
    with ExcelReader(path) as book:
        rows = book.read_rows_as_dicts(SHEET_NAME)

    entries: dict[int, ReportEntry] = {}
    for offset, row in enumerate(rows):
        row_number = offset + _FIRST_DATA_ROW
        if _is_blank_row(row):
            continue  # 表の下に残った空行は読み飛ばす
        entry = _to_entry(row, row_number)
        if entry.key in entries:
            raise DuplicateReportKeyError(entry.key, path)
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


def _is_blank_row(row: dict) -> bool:
    """すべての列が空の行か。"""
    return all(value in (None, "") for value in row.values())


def _to_entry(row: dict, row_number: int) -> ReportEntry:
    """1行を ReportEntry にする。書き方が正しくなければ、行と列を示して止める。"""
    key = _to_key(row.get(KEY_COLUMN), row_number)
    url = _to_text(row.get(URL_COLUMN), row_number, URL_COLUMN)
    try:
        report_id = report_id_from_url(url)
    except SalesforceReportIdNotFoundError as e:
        raise InvalidReportEntryError(row_number, URL_COLUMN, url, str(e)) from e

    schedule = _to_text(row.get(SCHEDULE_COLUMN), row_number, SCHEDULE_COLUMN)
    if schedule not in SCHEDULES:
        raise InvalidReportEntryError(
            row_number,
            SCHEDULE_COLUMN,
            schedule,
            f"「{SCHEDULED}」か「{ON_DEMAND}」と書いてください。",
        )

    return ReportEntry(
        key=key,
        summary=_to_text(row.get(SUMMARY_COLUMN), row_number, SUMMARY_COLUMN),
        url=url,
        report_id=report_id,
        schedule=schedule,
        folder=Path(_to_text(row.get(FOLDER_COLUMN), row_number, FOLDER_COLUMN)),
        enabled=_to_enabled(row.get(ENABLED_COLUMN)),
    )


def _to_key(value: object, row_number: int) -> int:
    """管理番号を整数にする。Excel は数値を小数で返すことがあるので丸めずに検査する。"""
    if isinstance(value, bool) or value in (None, ""):
        raise InvalidReportEntryError(row_number, KEY_COLUMN, value, "数字を入れてください。")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = str(value).strip()
    if not text.isdigit():
        raise InvalidReportEntryError(
            row_number, KEY_COLUMN, value, "数字だけで書いてください（例: 1001）。"
        )
    return int(text)


def _to_text(value: object, row_number: int, column: str) -> str:
    """空でない文字列にする。"""
    text = "" if value is None else str(value).strip()
    if not text:
        raise InvalidReportEntryError(row_number, column, value, "空のままにできません。")
    return text


def _to_enabled(value: object) -> bool:
    """「有効」列を真偽にする。空欄は有効として扱う（書き忘れで止めない）。"""
    if value in (None, ""):
        return True
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ENABLED_VALUES
