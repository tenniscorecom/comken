"""comken/services/salesforce_downloader/provider.py — 取得済みファイルの取り出し。

「取りに行く」関数ではなく「既に取ってあるものを受け取る」関数を置く場所。
**import 時に `requests` を読まない**（BO 環境で動かす前提）。
`comken.toolbox.salesforce` に依存しないことで、`requests` の入っていない環境でも
このモジュールだけを使えるようにする。

    from comken.services.salesforce_downloader import get_scheduled_report

    rows = get_scheduled_report("1001").read_rows()

戻り値を `CsvReader` にした理由は、利用側が `read_rows()` / `index()` / `filter()`
をそのまま使えること、そして **CsvWriter が何の文字コードで書いたかを利用側が
知らなくてよくなる**こと。`CsvReader` は最初のメソッド呼び出しまでファイルを読まない
（遅延読み込み）ので、パスだけ欲しい場合は `.path` で取れる。

このファイルが持つもの:
- 定期取得済みのファイルを返す
- 保存先パスの組み立て

ここに書かないもの:
- Salesforce への問い合わせ → service.py
- 履歴への記録 → history.py
- 管理表の読み込み（列定義・雛形・検査）→ master.py
"""

import logging
from pathlib import Path

from comken.core.files import DateNameBuilder
from comken.exceptions import (
    ReportDisabledError,
    ReportFileMissingError,
    ReportNotRegisteredError,
    ScheduledReportNotDownloadedError,
    ScheduledReportNotRegisteredError,
)
from comken.services.salesforce_downloader._paths import HISTORY_PATH, MASTER_PATH
from comken.services.salesforce_downloader.history import downloaded_today
from comken.services.salesforce_downloader.master import ReportEntry, load_master
from comken.toolbox.csv import CsvReader

logger = logging.getLogger(__name__)

# ── service.py から移動してきた定数 ──
SUFFIX = ".csv"
# ファイル名に使えない文字。概要をファイル名に混ぜるので、ここで落とす
_FORBIDDEN_IN_NAME = '\\/:*?"<>|'
# 概要が長いとパスが伸びすぎるので、ファイル名に使うのはこの長さまで
_SUMMARY_LIMIT = 30


def get_scheduled_report(report_key: str, project: str = "") -> CsvReader:
    """定期取得しておいたファイルを `CsvReader` で返す。**取りに行かない。**

    Args:
        report_key: 管理表の管理番号（例: "1001"）。
        project: 呼び出し元の名前（履歴には残さないが、例外の調査に使えるよう受け取る）。

    Returns:
        定期取得で保存されたファイルを読み取る `CsvReader`。ファイルパスは `.path` で取れる。

    Raises:
        ReportNotRegisteredError: 管理表に無い管理番号の場合。
        ReportDisabledError: 管理表で無効になっている場合。
        ScheduledReportNotRegisteredError: 管理表で「個別」になっている場合。
        ScheduledReportNotDownloadedError: 本日の定期取得がまだ済んでいない場合。
        ReportFileMissingError: 履歴では取得済みだが、ファイルが無い場合。
    """
    entry = _find(report_key, MASTER_PATH)
    if not entry.is_scheduled:
        raise ScheduledReportNotRegisteredError(
            entry.key, entry.summary, entry.schedule, MASTER_PATH
        )
    if not downloaded_today(HISTORY_PATH, entry.key):
        raise ScheduledReportNotDownloadedError(entry.key, entry.summary, HISTORY_PATH)

    path = file_path_of(entry)
    if not path.is_file():
        raise ReportFileMissingError(entry.key, path)
    logger.info("定期取得済みのファイルを使います: %s", path)
    return CsvReader(path)


def file_path_of(entry: ReportEntry) -> Path:
    """そのレポートを保存するパス。

    ファイル名は「管理番号_概要_日付」。**管理番号を先頭に置く**のは、概要や
    参照先の Salesforce レポートが変わっても、番号は変わらないため。概要を入れるのは、
    保存先を人が直接見たときに何のファイルか分かるようにするため。
    """
    name = f"{entry.key}_{_safe_summary(entry.summary)}"
    return entry.folder / DateNameBuilder(name, ext=SUFFIX).suffix()


def _find(report_key: str, master_path: Path) -> ReportEntry:
    """管理表から1行を引く。無効なものはここで止める。"""
    entries = load_master(master_path)
    entry = entries.get(report_key)
    if entry is None:
        raise ReportNotRegisteredError(report_key, sorted(entries), master_path)
    if not entry.enabled:
        raise ReportDisabledError(entry.key, entry.summary, master_path)
    return entry


def _safe_summary(summary: str) -> str:
    """概要をファイル名に使える形にする。"""
    cleaned = "".join(char for char in summary if char not in _FORBIDDEN_IN_NAME).strip()
    return cleaned[:_SUMMARY_LIMIT] or "レポート"
