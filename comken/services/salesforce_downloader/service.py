r"""comken/services/salesforce_downloader/service.py — 取得の本体。

    from comken.services.salesforce_downloader import download_report, get_scheduled_report

    CUSTOMER_LIST = 1001          # 各プロジェクトで、意味の分かる名前を付ける

    path = download_report(CUSTOMER_LIST)        # 今すぐ Salesforce から取る
    path = get_scheduled_report(CUSTOMER_LIST)   # 定期取得しておいたものを受け取る

**2つの関数の意味をはっきり分ける。**

- `download_report()` は「**今この瞬間に取りに行く**」。管理表で定期になっていても、
  今日すでに取っていても、必ず Salesforce へ問い合わせる。呼んだ側が最新を求めている
  のだから、黙って前のものを返さない。
- `get_scheduled_report()` は「**取っておいたものを受け取る**」。取りに行く関数ではない。
  まだ取れていなければ例外にする。ここで自動的に取りに行くと、**定期取得が動いて
  いないことに誰も気づかなくなる**。

プロジェクト側のコードに Salesforce の URL もレポート ID も現れない。管理表の
参照先を差し替えても、`CUSTOMER_LIST = 1001` はそのままでよい。
"""

import logging
import time
from pathlib import Path

from ...exceptions import (
    ComkenError,
    EmptyReportError,
    ReportDisabledError,
    ReportFileMissingError,
    ReportFolderNotFoundError,
    ReportNotRegisteredError,
    ScheduledDownloadFailedError,
    ScheduledReportNotDownloadedError,
    ScheduledReportNotRegisteredError,
)
from ...toolbox.csv import CsvWriter
from ...toolbox.salesforce.sites import site_for
from ...toolbox.utils.files import DateNameBuilder
from . import history
from .master import ReportEntry, load_master, shared_report_ids

logger = logging.getLogger(__name__)

# ── 配置時に実際の場所へ書き換える（このリポジトリは公開しているので仮名にしてある）──
# 管理表。非エンジニアが「このレポートをこの名前で」と足すのはこのファイル
MASTER_PATH = Path(r"\\server\share\tools\salesforce\レポート管理表.xlsx")
# ダウンロード履歴。プログラムが追記する（人は編集しない）
HISTORY_PATH = Path(r"\\server\share\tools\salesforce\ダウンロード履歴.csv")

SUFFIX = ".csv"
# ファイル名に使えない文字。概要をファイル名に混ぜるので、ここで落とす
_FORBIDDEN_IN_NAME = '\\/:*?"<>|'
# 概要が長いとパスが伸びすぎるので、ファイル名に使うのはこの長さまで
_SUMMARY_LIMIT = 30


def download_report(
    report_key: int,
    project: str = "",
    *,
    master_path: Path | None = None,
    history_path: Path | None = None,
) -> Path:
    """今すぐ Salesforce から取得して保存し、そのパスを返す。

    **必ず Salesforce へ問い合わせる。** 今日すでに取っていても取り直す。

    Args:
        report_key: 管理表の管理番号（例: 1001）。
        project: 呼び出し元の名前。履歴に残るので、入れておくと後から追える。
        master_path: 管理表のパス（省略時は MASTER_PATH。通常は省略する）。
        history_path: 履歴のパス（省略時は HISTORY_PATH。通常は省略する）。

    Returns:
        保存したファイルのパス。

    Raises:
        ReportNotRegisteredError: 管理表に無い管理番号の場合。
        ReportDisabledError: 管理表で無効になっている場合。
        ReportFolderNotFoundError: 保存先のフォルダが無い場合。
        EmptyReportError: 明細が 0 行だった場合。
    """
    master_path = master_path or MASTER_PATH
    history_path = history_path or HISTORY_PATH
    entry = _find(report_key, master_path)
    return _download(entry, project, history.TRIGGER_ON_DEMAND, history_path)


def get_scheduled_report(
    report_key: int,
    project: str = "",
    *,
    master_path: Path | None = None,
    history_path: Path | None = None,
) -> Path:
    """定期取得しておいたファイルのパスを返す。**取りに行かない。**

    Args:
        report_key: 管理表の管理番号（例: 1001）。
        project: 呼び出し元の名前（履歴には残さないが、例外の調査に使えるよう受け取る）。
        master_path: 管理表のパス（省略時は MASTER_PATH。通常は省略する）。
        history_path: 履歴のパス（省略時は HISTORY_PATH。通常は省略する）。

    Returns:
        定期取得で保存されたファイルのパス。

    Raises:
        ReportNotRegisteredError: 管理表に無い管理番号の場合。
        ScheduledReportNotRegisteredError: 管理表で「個別」になっている場合。
        ScheduledReportNotDownloadedError: 本日の定期取得がまだ済んでいない場合。
        ReportFileMissingError: 履歴では取得済みだが、ファイルが無い場合。
    """
    master_path = master_path or MASTER_PATH
    history_path = history_path or HISTORY_PATH
    entry = _find(report_key, master_path)
    if not entry.is_scheduled:
        raise ScheduledReportNotRegisteredError(
            entry.key, entry.summary, entry.schedule, master_path
        )
    if not history.downloaded_today(history_path, entry.key):
        raise ScheduledReportNotDownloadedError(entry.key, entry.summary, history_path)

    path = file_path_of(entry)
    if not path.is_file():
        raise ReportFileMissingError(entry.key, path)
    logger.info("定期取得済みのファイルを使います: %s", path)
    return path


def download_scheduled(
    project: str = "定期実行", *, master_path: Path | None = None, history_path: Path | None = None
) -> list[Path]:
    """管理表で「定期」かつ有効なレポートをまとめて取得する。

    定期実行のプロジェクトから呼ぶ。**1件失敗しても残りは続ける** ——
    5本のうち1本が落ちたときに全部やり直すと、手で用意する手間が5本ぶんになる。

    Args:
        project: 履歴に残す呼び出し元の名前。
        master_path: 管理表のパス（省略時は MASTER_PATH。通常は省略する）。
        history_path: 履歴のパス（省略時は HISTORY_PATH。通常は省略する）。

    Returns:
        取得できたファイルのパス。

    Raises:
        ScheduledDownloadFailedError: 1件でも取得できなかった場合。
            **取得できたものは保存したうえで**送出する。ログだけに出して正常終了すると、
            スケジューラや RPA 基盤から見て成功と区別が付かない。
    """
    master_path = master_path or MASTER_PATH
    history_path = history_path or HISTORY_PATH
    entries = load_master(master_path)
    _warn_shared_reports(entries)

    targets = [entry for entry in entries.values() if entry.is_scheduled and entry.enabled]
    logger.info("定期取得の対象: %d 件", len(targets))

    saved: list[Path] = []
    failed: list[int] = []
    for entry in targets:
        try:
            saved.append(_download(entry, project, history.TRIGGER_SCHEDULED, history_path))
        except ComkenError as e:
            # 1件の失敗で残りを落とさない。失敗は履歴とログに残る
            logger.error("取得に失敗しました: %s（%s）", entry.key, e)
            failed.append(entry.key)

    logger.info("定期取得: %d 件中 %d 件を取得しました。", len(targets), len(saved))
    if failed:
        # 続けたぶん、最後に必ず知らせる（終了コードで落ちたことが分かるように）
        raise ScheduledDownloadFailedError(failed, history_path)
    return saved


def file_path_of(entry: ReportEntry) -> Path:
    """そのレポートを保存するパス。

    ファイル名は「管理番号_概要_日付」。**管理番号を先頭に置く**のは、概要や
    参照先の Salesforce レポートが変わっても、番号は変わらないため。概要を入れるのは、
    保存先を人が直接見たときに何のファイルか分かるようにするため。
    """
    name = f"{entry.key}_{_safe_summary(entry.summary)}"
    return entry.folder / DateNameBuilder(name, SUFFIX).suffix()


def _find(report_key: int, master_path: Path) -> ReportEntry:
    """管理表から1行を引く。無効なものはここで止める。"""
    entries = load_master(master_path)
    entry = entries.get(report_key)
    if entry is None:
        raise ReportNotRegisteredError(report_key, sorted(entries), master_path)
    if not entry.enabled:
        raise ReportDisabledError(entry.key, entry.summary, master_path)
    return entry


def _download(entry: ReportEntry, project: str, trigger: str, history_path: Path) -> Path:
    """1件を取得して保存し、成否を履歴に残す。"""
    path = file_path_of(entry)
    started = time.perf_counter()
    try:
        if not entry.folder.is_dir():
            # 作らずに失敗させる。無いのは書き間違いのことが多く、勝手に作ると
            # 誰も読まない場所へ置き続けることになる
            raise ReportFolderNotFoundError(entry.key, entry.folder)

        rows = _fetch(entry)
        if not rows:
            raise EmptyReportError(entry.key, entry.summary, entry.url)
        _write_csv(path, rows)
    except ComkenError as e:
        history.record(
            history_path,
            report_key=entry.key,
            summary=entry.summary,
            report_id=entry.report_id,
            url=entry.url,
            project=project,
            trigger=trigger,
            succeeded=False,
            fetched_from_salesforce=True,
            folder=entry.folder,
            seconds=time.perf_counter() - started,
            error=str(e),
        )
        raise

    seconds = time.perf_counter() - started
    history.record(
        history_path,
        report_key=entry.key,
        summary=entry.summary,
        report_id=entry.report_id,
        url=entry.url,
        project=project,
        trigger=trigger,
        succeeded=True,
        fetched_from_salesforce=True,
        folder=entry.folder,
        file_name=path.name,
        row_count=len(rows),
        seconds=seconds,
    )
    logger.info("取得しました: %s（%d 行 / %.1f 秒）", path, len(rows), seconds)
    return path


def _fetch(entry: ReportEntry) -> list[dict]:
    """Salesforce へ問い合わせて明細行を返す。

    つなぐ組織は URL のドメインで決まる（`site_for()`）。管理表に組織を選ぶ列は
    作らない——人が選ぶ形にすると、URL と食い違ったときに別の組織へ問い合わせて
    「レポートが見つからない」という分かりにくい失敗になる。
    """
    site = site_for(entry.url)
    with site() as salesforce:
        return salesforce.report.run(entry.report_id)


def _write_csv(path: Path, rows: list[dict]) -> None:
    """一時ファイルへ書いてから置き換える。

    複数のプロジェクトが同時に呼ぶので、直接書くと**読んでいる最中のファイルが
    半端な状態**になりうる。同じフォルダ内の置き換えは一度に入れ替わる。
    """
    tmp_path = history.new_temp_name(path)
    try:
        CsvWriter(tmp_path, list(rows[0])).write_rows(rows)
        tmp_path.replace(path)
    finally:
        tmp_path.unlink(missing_ok=True)  # 途中で失敗したときに残骸を残さない


def _warn_shared_reports(entries: dict[int, ReportEntry]) -> None:
    """同じ Salesforce レポートを複数の管理番号が指していればログに出す。

    エラーにはしない（意図している場合もある）。**気づけるようにするだけ**。
    """
    for report_id, keys in shared_report_ids(entries).items():
        logger.info(
            "同じ Salesforce レポートを %d 件の管理番号が指しています: %s（%s）",
            len(keys),
            "、".join(str(key) for key in keys),
            report_id,
        )


def _safe_summary(summary: str) -> str:
    """概要をファイル名に使える形にする。"""
    cleaned = "".join(char for char in summary if char not in _FORBIDDEN_IN_NAME).strip()
    return cleaned[:_SUMMARY_LIMIT] or "レポート"
