"""comken/services/salesforce_downloader/provider.py — 取得済みファイルの取り出し。

「取りに行く」関数ではなく「既に取ってあるものを受け取る」関数を置く場所。
**import 時に `requests` を読まない**（BO 環境で動かす前提）。
`comken.toolbox.salesforce` に依存しないことで、`requests` の入っていない環境でも
このモジュールだけを使えるようにする。

    from comken.services.salesforce_downloader import cached_report

    rows = cached_report("1001").read()

戻り値は `Table`。行の検索・抽出・索引化は Table の API でできる。
パスだけ欲しい場合は `cached_report_path()` を使う。

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
from comken.core.table.model import Table
from comken.core.timer import measure
from comken.exceptions import (
    CachedReportNotFoundError,
    CachedReportNotRegisteredError,
    ReportDisabledError,
    ReportNotRegisteredError,
)
from comken.services.salesforce_downloader._paths import MASTER_PATH
from comken.services.salesforce_downloader.master import ReportEntry, load_master
from comken.toolbox.csv import CSV

logger = logging.getLogger(__name__)

# ── service.py から移動してきた定数 ──
SUFFIX = ".csv"
# ファイル名に使えない文字。概要をファイル名に混ぜるので、ここで落とす
_FORBIDDEN_IN_NAME = '\\/:*?"<>|'
# 概要が長いとパスが伸びすぎるので、ファイル名に使うのはこの長さまで
_SUMMARY_LIMIT = 30


@measure
def cached_report(report_key: str, project: str = "") -> Table:
    """本日の定期取得キャッシュを `Table` で返す。**取りに行かない。**

    Args:
        report_key: 管理表の管理番号（例: "1001"）。
        project: 呼び出し元の名前（履歴には残さないが、例外の調査に使えるよう受け取る）。

    Returns:
        本日の最新キャッシュから読み取った `Table`。

    Raises:
        ReportNotRegisteredError: 管理表に無い管理番号の場合。
        ReportDisabledError: 管理表で無効になっている場合。
        CachedReportNotRegisteredError: 管理表で「個別」になっている場合。
        CachedReportNotFoundError: 本日のキャッシュが無い場合。
    """
    entry = _find(report_key, MASTER_PATH)
    if not entry.is_scheduled:
        raise CachedReportNotRegisteredError(entry.key, entry.summary, entry.schedule, MASTER_PATH)
    path = _daily_cache_path_of(entry)
    if not path.is_file():
        raise CachedReportNotFoundError(entry.key, entry.summary, path)
    logger.info("本日の定期取得キャッシュを使います: %s", path)
    with CSV(path, read_only=True, columns=[] if path.stat().st_size == 0 else None) as csv_file:
        return csv_file.read()


@measure
def cached_report_path(report_key: str) -> Path:
    """本日の定期取得キャッシュが置かれるパスを返す。中身は読まない。

    ファイル自体を別のツールに渡したいときに使う。**取りに行かない。**

    Args:
        report_key: 管理表の管理番号（例: "1001"）。

    Returns:
        本日の最新キャッシュとして使われる `Path`。

    Raises:
        ReportNotRegisteredError: 管理表に無い管理番号の場合。
        ReportDisabledError: 管理表で無効になっている場合。
        CachedReportNotRegisteredError: 管理表で「個別」になっている場合。
    """
    entry = _find(report_key, MASTER_PATH)
    if not entry.is_scheduled:
        raise CachedReportNotRegisteredError(entry.key, entry.summary, entry.schedule, MASTER_PATH)
    return _daily_cache_path_of(entry)


def file_path_of(entry: ReportEntry) -> Path:
    """そのレポートを保存するパス。

    ファイル名は「管理番号_概要_日付_時刻_マイクロ秒」。**管理番号を先頭に置く**のは、概要や
    参照先の Salesforce レポートが変わっても、番号は変わらないため。概要を入れるのは、
    保存先を人が直接見たときに何のファイルか分かるようにするため。
    """
    name = f"{entry.key}_{_safe_summary(entry.summary)}{SUFFIX}"
    return entry.folder / DateNameBuilder(name).suffix("%Y%m%d_%H%M%S_%f")


def _daily_cache_path_of(entry: ReportEntry) -> Path:
    """定期取得の当日最新キャッシュに使う固定パスを返す。

    時刻を含めないことで、同日に何度取得しても読む側が同じパスを直接確認できる。
    """
    name = f"{entry.key}_{_safe_summary(entry.summary)}{SUFFIX}"
    return entry.folder / DateNameBuilder(name).suffix("%Y%m%d")


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
