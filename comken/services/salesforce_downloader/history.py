"""comken/services/salesforce_downloader/history.py — ダウンロード履歴の記録。

**管理表とは別のファイルにする。** 書く主体が違う（管理表は人、履歴はプログラム）ので
分けないと、人が開いている間にプログラムが保存できず履歴が飛ぶ。**CSV に追記する。**
複数のプロジェクトが同時に走るので、Excel を開いて保存し直す方式だと壊れる。

成功／失敗の判断と各段階の結果（Salesforce への問い合わせ、保存）は呼ぶ側
（`service.py`）が決めて、ここは受け取った値を1行に書くだけ。集計は利用側で
この CSV を `CsvReader` で読む。
"""

import csv
import datetime
import logging
from dataclasses import dataclass
from pathlib import Path

from comken.core.clock import now, today
from comken.services.salesforce_downloader.master import ReportEntry

logger = logging.getLogger(__name__)

# 履歴CSVの列。順序は出力ファイルそのものなので、追加・並び替えは全プロジェクトの
# 既存履歴を読む処理へ影響する（互換性ポリシーに従う）
COLUMNS = (
    "実行日時",
    "管理番号",
    "概要",
    "レポートID",
    "URL",
    "プロジェクト",
    "実行方式",
    "成否",
    "Salesforce取得結果",  # 成功 / 失敗 / 空（その段階まで到達しなかった）
    "保存結果",  # 成功 / 失敗 / 空（その段階まで到達しなかった）
    "保存先",
    "ファイル名",
    "取得件数",
    "処理秒数",
    # 成功時は空。失敗時のみ、設定 / Salesforce / ファイル / データなし / プログラムの5値
    "原因区分",
    "エラーコード",  # 例外クラス名。成功時・到達しなかった段階は空
    "エラー内容",
)

SUCCESS = "成功"
FAILURE = "失敗"

# 呼ばれ方。定期実行でまとめて取ったのか、プロジェクトがその場で要求したのか
TRIGGER_SCHEDULED = "定期"
TRIGGER_ON_DEMAND = "個別"

_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True)
class HistoryRow:
    """履歴1行の「呼び出し側が組み立てる部分」。履歴の列と1対1。

    `entry` の5列（管理番号・概要・レポートID・URL・保存先）は `record()` 側で
    取り出す。`fetched_from_salesforce` / `saved_to_file` は `True` / `False` /
    `None` の3状態で、未到達は `None`。
    """

    succeeded: bool
    fetched_from_salesforce: bool | None
    saved_to_file: bool | None
    file_name: str = ""
    row_count: int | None = None
    seconds: float = 0.0
    cause: str = ""
    error_code: str = ""
    error: str = ""


def _stage(value: bool | None) -> str:
    """3状態（成功／失敗／未到達）を履歴の文字列に変換する。"""
    if value is None:
        return ""
    return SUCCESS if value else FAILURE


def record(
    path: str | Path,
    *,
    entry: ReportEntry,
    project: str,
    trigger: str,
    row: HistoryRow,
) -> None:
    """履歴を1行追記する。ファイルが無ければ見出し行から作る。

    **記録に失敗しても、呼び出し元の処理は止めない。** 履歴は後から振り返るための
    ものなので、取得できたのに履歴が書けないというだけで業務を止める理由がない。

    Args:
        path: 履歴 CSV のパス。
        entry: 管理表1行。管理番号・概要・レポートID・URL・保存先はこの中身を履歴に出す。
        project: 呼び出したプロジェクト名。
        trigger: TRIGGER_SCHEDULED か TRIGGER_ON_DEMAND。
        row: 履歴1行の本体（成否・各段階の結果・件数・エラー）。
    """
    path = Path(path)
    values = [
        now().strftime(_TIMESTAMP_FORMAT),
        entry.key,
        entry.summary,
        entry.report_id,
        entry.url,
        project,
        trigger,
        SUCCESS if row.succeeded else FAILURE,
        _stage(row.fetched_from_salesforce),
        _stage(row.saved_to_file),
        str(entry.folder),
        row.file_name,
        "" if row.row_count is None else row.row_count,
        f"{row.seconds:.2f}",
        row.cause,
        row.error_code,
        row.error.replace("\n", " "),  # 1行1レコードを保つ
    ]
    try:
        _append(path, values)
    except OSError as e:
        logger.warning("履歴を記録できませんでした: %s（%s）", path, e)


def downloaded_today(
    path: str | Path,
    report_key: str,
    trigger: str = TRIGGER_SCHEDULED,
    date: datetime.date | None = None,
) -> bool:
    """その日の取得が成功しているかを履歴から調べる。

    **ファイルの有無ではなく履歴で判定する。** 保存先に今日の日付のファイルがあっても、
    それが定期取得で置かれたのか、誰かが個別に取ったのか、手で置いたのかは分からない。
    「定期取得が動いているか」を知りたいので、履歴を正とする。

    Args:
        path: 履歴 CSV のパス。
        report_key: 管理番号。
        trigger: 数える呼ばれ方（既定は定期）。
        date: 調べる日付。省略すると今日。

    Returns:
        その日に成功した記録があれば True。履歴が無ければ False。
    """
    path = Path(path)
    if not path.is_file():
        return False

    target = (date or today()).strftime("%Y-%m-%d")
    key_text = str(report_key)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if (
                row.get("実行日時", "").startswith(target)
                and row.get("管理番号", "") == key_text
                and row.get("実行方式", "") == trigger
                and row.get("成否", "") == SUCCESS
            ):
                return True
    return False


def _append(path: Path, values: list) -> None:
    """1行を追記する。見出し行はファイルを作るときだけ書く。

    Excel が読めるよう UTF-8 BOM 付きにする。newline="" は csv モジュールの作法
    （Windows で空行が入るのを防ぐ）。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(COLUMNS)
        writer.writerow(values)
