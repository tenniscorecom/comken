r"""comken/services/salesforce_downloader/history.py — ダウンロード履歴の記録。

**管理表とは別のファイルにする。** 管理表は人が Excel で編集し、履歴はプログラムが
書き足す。同じファイルにすると、人が開いている間はプログラムが保存できず、
履歴が飛ぶか管理表が壊れる。書く主体が違うものは分ける。

**CSV に追記する。** 複数のプロジェクトが同時に呼ぶので、Excel を開いて保存し直す
方式だと壊れる。CSV への追記なら1行ずつ足すだけで済み、見るときは Excel で開ける。

この履歴から、あとで次のことが分かる。

- どのプロジェクトが、どのレポートを、どれくらいの頻度で使っているか
- 同じ Salesforce レポートを複数のプロジェクトが取りに行っていないか
- Salesforce へ実際に何回問い合わせたか（＝ API をどれだけ使っているか）
- 失敗がいつ・何回起きているか
"""

import csv
import datetime
import logging
import uuid
from pathlib import Path

from ...toolbox.utils.clock import now, today

logger = logging.getLogger(__name__)

COLUMNS = (
    "実行日時",
    "管理番号",
    "概要",
    "レポートID",
    "URL",
    "プロジェクト",
    "実行方式",
    "成否",
    "Salesforce取得",
    "保存先",
    "ファイル名",
    "取得件数",
    "処理秒数",
    "エラー内容",
)

SUCCESS = "成功"
FAILURE = "失敗"

# 呼ばれ方。定期実行でまとめて取ったのか、プロジェクトがその場で要求したのか
TRIGGER_SCHEDULED = "定期"
TRIGGER_ON_DEMAND = "個別"

_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def record(
    path: str | Path,
    *,
    report_key: int,
    summary: str,
    report_id: str,
    url: str,
    project: str,
    trigger: str,
    succeeded: bool,
    fetched_from_salesforce: bool,
    folder: Path | None = None,
    file_name: str = "",
    row_count: int | None = None,
    seconds: float | None = None,
    error: str = "",
) -> None:
    """履歴を1行追記する。ファイルが無ければ見出し行から作る。

    **記録に失敗しても、呼び出し元の処理は止めない。** 履歴は後から振り返るための
    ものなので、取得できたのに履歴が書けないというだけで業務を止める理由がない。

    Args:
        path: 履歴 CSV のパス。
        report_key: 管理番号。
        summary: 概要（管理表の説明）。
        report_id: Salesforce のレポート ID。
        url: レポートの URL。
        project: 呼び出したプロジェクト名。
        trigger: TRIGGER_SCHEDULED か TRIGGER_ON_DEMAND。
        succeeded: 取得できたか。
        fetched_from_salesforce: 実際に Salesforce へ問い合わせたか。
        folder: 保存先フォルダ。
        file_name: 保存したファイル名。
        row_count: 取得できた件数。
        seconds: かかった秒数。
        error: 失敗した場合のエラー内容。
    """
    path = Path(path)
    row = [
        now().strftime(_TIMESTAMP_FORMAT),
        report_key,
        summary,
        report_id,
        url,
        project,
        trigger,
        SUCCESS if succeeded else FAILURE,
        "○" if fetched_from_salesforce else "",
        str(folder) if folder else "",
        file_name,
        "" if row_count is None else row_count,
        "" if seconds is None else f"{seconds:.2f}",
        error.replace("\n", " "),  # 1行1レコードを保つ
    ]
    try:
        _append(path, row)
    except OSError as e:
        logger.warning("履歴を記録できませんでした: %s（%s）", path, e)


def downloaded_today(
    path: str | Path,
    report_key: int,
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


def _append(path: Path, row: list) -> None:
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
        writer.writerow(row)


def new_temp_name(path: Path) -> Path:
    """同じフォルダに作る一時ファイル名（毎回変える）。

    - 同時に走っても互いを壊さないよう、名前に乱数を入れる
    - **`~` で始める**ので、使う側が「1001_*.csv」で探しても拾わない
    - 拡張子は元のまま（CsvWriter は .csv 以外を受け付けない）
    """
    return path.with_name(f"~{path.stem}.{uuid.uuid4().hex}{path.suffix}")
