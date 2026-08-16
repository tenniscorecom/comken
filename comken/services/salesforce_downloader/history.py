"""comken/services/salesforce_downloader/history.py — ダウンロード履歴の記録。

**管理表とは別のファイルにする。** 管理表は人が Excel で編集し、履歴はプログラムが
書き足す。同じファイルにすると、人が開いている間はプログラムが保存できず、
履歴が飛ぶか管理表が壊れる。書く主体が違うものは分ける。

**CSV に追記する。** 複数のプロジェクトが同時に呼ぶので、Excel を開いて保存し直す
方式だと壊れる。CSV への追記なら1行ずつ足すだけで済み、見るときは Excel で開ける。

この履歴から、あとで次のことが分かる。

- どのプロジェクトが、どのレポートを、どれくらいの頻度で使っているか
- 同じ Salesforce レポートを複数のプロジェクトが取りに行っていないか
- Salesforce へ実際に何回問い合わせたか（＝ API をどれだけ使っているか）
- 失敗がいつ・何回起きているか、どの段階で失敗したか

成功／失敗の判断と各段階の結果（Salesforce への問い合わせ、保存）は呼ぶ側
（`service.py`）が決めて、ここは受け取った値を1行に書くだけ。履歴を集計・分析
したい場合は、利用プロジェクト側でこの CSV を `CsvReader` で読む。

このファイルが持つもの:
- 履歴CSVの列を決める
- 1行追記する
- その日の定期取得が成功しているかを履歴から答える

ここに書かないもの:
- 成功／失敗の判断 → 呼ぶ側（service.py）が決めて渡す。ここは受け取った結果を書くだけ
- 履歴の集計・分析（月別の件数、失敗の多いレポートの抽出など）
  → 利用プロジェクトで、この CSV を CsvReader で読んで集計する
- 取得や保存そのもの → service.py
"""

import csv
import datetime
import logging
import uuid
from pathlib import Path

from ...toolbox.utils.clock import now, today

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
    "原因区分",  # 成功時は空。失敗時のみ、設定 / Salesforce / ファイル / プログラムの4値
    "エラーコード",  # 例外クラス名。成功時・到達しなかった段階は空
    "エラー内容",
)

SUCCESS = "成功"
FAILURE = "失敗"

# 呼ばれ方。定期実行でまとめて取ったのか、プロジェクトがその場で要求したのか
TRIGGER_SCHEDULED = "定期"
TRIGGER_ON_DEMAND = "個別"

_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def _stage(value: bool | None) -> str:
    """3状態（成功／失敗／未到達）を履歴の文字列に変換する。"""
    if value is None:
        return ""
    return SUCCESS if value else FAILURE


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
    fetched_from_salesforce: bool | None,
    saved_to_file: bool | None,
    folder: Path | None = None,
    file_name: str = "",
    row_count: int | None = None,
    seconds: float | None = None,
    cause: str = "",
    error_code: str = "",
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
        succeeded: 全体の成否。
        fetched_from_salesforce: Salesforce への問い合わせ結果（True=成功 / False=失敗 /
            None=その段階まで到達しなかった）。
        saved_to_file: ファイル保存の結果（True=成功 / False=失敗 /
            None=その段階まで到達しなかった）。
        folder: 保存先フォルダ。
        file_name: 保存したファイル名。
        row_count: 取得できた件数。
        seconds: かかった秒数。
        cause: 失敗の原因区分（`設定` / `Salesforce` / `ファイル` / `プログラム`）。
            成功時は空文字。判定は呼ぶ側（`service.py`）が行う。
        error_code: 例外クラス名（`ERRORS.md` と1対1で引ける）。成功時・到達しなかった
            段階は空文字。
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
        _stage(fetched_from_salesforce),
        _stage(saved_to_file),
        str(folder) if folder else "",
        file_name,
        "" if row_count is None else row_count,
        "" if seconds is None else f"{seconds:.2f}",
        cause,
        error_code,
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
