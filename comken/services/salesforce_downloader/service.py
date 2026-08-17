r"""comken/services/salesforce_downloader/service.py — 取得の本体。

    from comken.services.salesforce_downloader import download_report, get_scheduled_report

    CUSTOMER_LIST = "1001"        # 各プロジェクトで、意味の分かる名前を付ける

    rows = download_report(CUSTOMER_LIST).read_rows()        # 今すぐ Salesforce から取る
    by_code = get_scheduled_report(CUSTOMER_LIST).index("顧客コード")   # 定期取得済みを読む

**2つの関数の意味をはっきり分ける。**

- `download_report()` は「**今この瞬間に取りに行く**」。管理表で定期になっていても、
  今日すでに取っていても、必ず Salesforce へ問い合わせる。呼んだ側が最新を求めている
  のだから、黙って前のものを返さない
- `get_scheduled_report()` は「**取っておいたものを受け取る**」。取りに行く関数ではない。
  まだ取れていなければ例外にする。ここで自動的に取りに行くと、**定期取得が動いて
  いないことに誰も気づかなくなる**

戻り値を `CsvReader` にした理由は、利用側が `read_rows()` / `index()` / `filter()`
をそのまま使えること、そして **CsvWriter が何の文字コードで書いたかを利用側が
知らなくてよくなる**こと。`CsvReader` は最初のメソッド呼び出しまでファイルを読まない
（遅延読み込み）ので、パスだけ欲しい場合は `.path` で取れる（読込みは走らない）。
`download_scheduled()` は定期取得したパスのリストを `list[Path]` で返すが、これは
定期取得の呼び出し側が中身を読まず「取らせる」のが目的なので、reader を並べても
使い道がないため（役割の違いが戻り値の型に出ている）。

プロジェクト側のコードに Salesforce の URL もレポート ID も現れない。管理表の
参照先を差し替えても、`CUSTOMER_LIST = "1001"` はそのままでよい。

このファイルが持つもの:
- 1件を取得して保存し履歴に残す流れ
- 保存先パスの決め方
- 管理表・履歴の置き場所（`MASTER_PATH`・`HISTORY_PATH`）

ここに書かないもの:
- 「このプロジェクトのときは」という分岐 → 利用プロジェクト
- スケジュール判定（毎日・平日・月末など）→ 呼び出す側
- 管理表にどんな列があるか → master.py
- 履歴にどんな列があるか → history.py
- Salesforce の認証・API の叩き方 → comken/toolbox/salesforce/
"""

import logging
import time
from pathlib import Path

from comken.core.files import DateNameBuilder
from comken.exceptions import (
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
from comken.services.salesforce_downloader import history
from comken.services.salesforce_downloader.history import HistoryRow
from comken.services.salesforce_downloader.master import ReportEntry, load_master, shared_report_ids
from comken.toolbox.csv import CsvReader, CsvWriter
from comken.toolbox.salesforce.sites import site_for

logger = logging.getLogger(__name__)

# ── 配置するときに実際の場所へ書き換える（公開リポジトリなので仮名にしてある）──
# レポート管理表（Excel）。非エンジニアが編集する。雛形は次のコマンドで作れる:
#     python -m comken.services.salesforce_downloader init レポート管理表.xlsx
# **config ファイルへは外出ししない。** 利用側がパスを渡せるようにすると、
# プロジェクト側に定数を持たせて管理表と食い違う事故が起きる（場所を変えるなら
# ここ1か所を変える）。設定ファイルに集約する案は試して戻した
# （仕様書 8章「配置時に書き換える3ファイル」）。
MASTER_PATH = Path(r"\\server\share\tools\salesforce\レポート管理表.xlsx")

# ダウンロード履歴（CSV）。プログラムが追記する（人は編集しない）
HISTORY_PATH = Path(r"\\server\share\tools\salesforce\ダウンロード履歴.csv")

SUFFIX = ".csv"
# ファイル名に使えない文字。概要をファイル名に混ぜるので、ここで落とす
_FORBIDDEN_IN_NAME = '\\/:*?"<>|'
# 概要が長いとパスが伸びすぎるので、ファイル名に使うのはこの長さまで
_SUMMARY_LIMIT = 30

# 履歴の「原因区分」列に出す5値。運用する人が履歴からすぐ「誰が動くか」を判断できるように、
# 抽象クラス名ではなく誰が直すかで分ける（設計判断は docs/開発/仕様書.md 4.28 参照）
CAUSE_CONFIG = "設定"
CAUSE_SALESFORCE = "Salesforce"
CAUSE_EMPTY_DATA = "データなし"
CAUSE_FILE = "ファイル"
CAUSE_PROGRAM = "プログラム"


def download_report(report_key: str, project: str = "") -> CsvReader:
    """今すぐ Salesforce から取得して保存し、そのファイルを `CsvReader` で返す。

    **必ず Salesforce へ問い合わせる。** 今日すでに取っていても取り直す。

    Args:
        report_key: 管理表の管理番号（例: "1001"）。
        project: 呼び出し元の名前。履歴に残るので、入れておくと後から追える。

    Returns:
        保存したファイルを読み取る `CsvReader`。ファイルパスは `.path` で取れる。

    Raises:
        ReportNotRegisteredError: 管理表に無い管理番号の場合。
        ReportDisabledError: 管理表で無効になっている場合。
        ReportFolderNotFoundError: 保存先のフォルダが無い場合。
        EmptyReportError: 明細が 0 行だった場合。
    """
    entry = _find(report_key, MASTER_PATH)
    path = _download(entry, project, history.TRIGGER_ON_DEMAND, HISTORY_PATH)
    return CsvReader(path)


def get_scheduled_report(report_key: str, project: str = "") -> CsvReader:
    """定期取得しておいたファイルを `CsvReader` で返す。**取りに行かない。**

    Args:
        report_key: 管理表の管理番号（例: "1001"）。
        project: 呼び出し元の名前（履歴には残さないが、例外の調査に使えるよう受け取る）。

    Returns:
        定期取得で保存されたファイルを読み取る `CsvReader`。ファイルパスは `.path` で取れる。

    Raises:
        ReportNotRegisteredError: 管理表に無い管理番号の場合。
        ScheduledReportNotRegisteredError: 管理表で「個別」になっている場合。
        ScheduledReportNotDownloadedError: 本日の定期取得がまだ済んでいない場合。
        ReportFileMissingError: 履歴では取得済みだが、ファイルが無い場合。
    """
    entry = _find(report_key, MASTER_PATH)
    if not entry.is_scheduled:
        raise ScheduledReportNotRegisteredError(
            entry.key, entry.summary, entry.schedule, MASTER_PATH
        )
    if not history.downloaded_today(HISTORY_PATH, entry.key):
        raise ScheduledReportNotDownloadedError(entry.key, entry.summary, HISTORY_PATH)

    path = file_path_of(entry)
    if not path.is_file():
        raise ReportFileMissingError(entry.key, path)
    logger.info("定期取得済みのファイルを使います: %s", path)
    return CsvReader(path)


def download_scheduled(project: str = "定期実行") -> list[Path]:
    """管理表で「定期」かつ有効なレポートをまとめて取得する。

    定期実行のプロジェクトから呼ぶ。**1件失敗しても残りは続ける**。戻り値は `list[Path]`
    のままで `CsvReader` を返さない（定期取得の呼び出し側は中身を読まないため）。

    Raises:
        ScheduledDownloadFailedError: 1件でも取得できなかった場合。**取得できたものは
            保存したうえで**送出する。ログだけに出して正常終了すると、スケジューラや
            RPA 基盤から見て成功と区別が付かない。
    """
    entries = load_master(MASTER_PATH)
    _warn_shared_reports(entries)

    targets = [entry for entry in entries.values() if entry.is_scheduled and entry.enabled]
    logger.info("定期取得の対象: %d 件", len(targets))

    saved: list[Path] = []
    failed: list[str] = []
    for entry in targets:
        try:
            saved.append(_download(entry, project, history.TRIGGER_SCHEDULED, HISTORY_PATH))
        except (ComkenError, OSError) as e:
            # **想定した失敗は続ける。想定していない失敗は止める。**
            # - `ComkenError` は `docs/ERRORS.md` に対処法が載っている想定内の失敗なので続行する
            # - `OSError` は共有サーバー断・権限・パスなど運用上の失敗。保存先は
            #   レポートごとに違うので、1本ダメでも他は書けるので続行する
            # - それ以外（`TypeError` などプログラムのバグ）は想定していない。
            #   `ScheduledDownloadFailedError`（＝「1件取れませんでした」）の顔で
            #   出てくると、非エンジニアが「もう一度実行してみる」を繰り返すだけなので、
            #   ここでは捕捉せず、その場で落として気づかせる
            # KeyboardInterrupt など処理中断を示す例外は `ComkenError` / `OSError` の
            # どちらでもないので、これもそのまま抜ける
            logger.error("取得に失敗しました: %s（%s）", entry.key, e)
            failed.append(entry.key)

    logger.info("定期取得: %d 件中 %d 件を取得しました。", len(targets), len(saved))
    if failed:
        # 続けたぶん、最後に必ず知らせる（終了コードで落ちたことが分かるように）
        raise ScheduledDownloadFailedError(failed, HISTORY_PATH)
    return saved


def file_path_of(entry: ReportEntry) -> Path:
    """そのレポートを保存するパス。

    ファイル名は「管理番号_概要_日付」。**管理番号を先頭に置く**のは、概要や
    参照先の Salesforce レポートが変わっても、番号は変わらないため。概要を入れるのは、
    保存先を人が直接見たときに何のファイルか分かるようにするため。
    """
    name = f"{entry.key}_{_safe_summary(entry.summary)}"
    return entry.folder / DateNameBuilder(name, SUFFIX).suffix()


def _find(report_key: str, master_path: Path) -> ReportEntry:
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
    started = time.perf_counter()
    try:
        _require_folder(entry)
        rows = _fetch(entry)
        path = _save(entry, rows)
    except Exception as exc:
        _record_failure(entry, project, trigger, history_path, exc, started)
        raise
    _record_success(entry, project, trigger, history_path, path, rows, started)
    return path


def _record_failure(
    entry: ReportEntry,
    project: str,
    trigger: str,
    history_path: Path,
    exc: BaseException,
    started: float,
) -> None:
    """失敗時の履歴とログ。`_download()` から呼ばれる。"""
    row = _failure_row(exc, time.perf_counter() - started)
    # 値を計算した場所（ここ）で、ログにも書く。`_download()` 抜けたあと
    # 別の層で「同じ値」を再利用することはない（後付けで属性を渡さない）
    logger.error("取得に失敗しました: %s（%s / 区分=%s）", entry.key, exc, row.cause)
    history.record(history_path, entry=entry, project=project, trigger=trigger, row=row)


def _record_success(
    entry: ReportEntry,
    project: str,
    trigger: str,
    history_path: Path,
    path: Path,
    rows: list[dict],
    started: float,
) -> None:
    """成功時の履歴とログ。`_download()` から呼ばれる。"""
    seconds = time.perf_counter() - started
    row = HistoryRow(
        succeeded=True,
        fetched_from_salesforce=True,
        saved_to_file=True,
        file_name=path.name,
        row_count=len(rows),
        seconds=seconds,
    )
    if rows:
        logger.info("取得しました: %s（%d 行 / %.1f 秒）", path, len(rows), seconds)
    else:
        logger.info("取得しました: %s（0 件 / 0件ありのため正常）", path)
    history.record(history_path, entry=entry, project=project, trigger=trigger, row=row)


def _require_folder(entry: ReportEntry) -> None:
    """保存先フォルダが無ければ `ReportFolderNotFoundError`。**勝手に作らない。**

    作らずに失敗させる。無いのは書き間違いのことが多く、勝手に作ると
    誰も読まない場所へ置き続けることになる。
    """
    if not entry.folder.is_dir():
        raise ReportFolderNotFoundError(entry.key, entry.folder)


def _fetch(entry: ReportEntry) -> list[dict]:
    """Salesforce へ問い合わせて明細行を返す。

    つなぐ組織は URL のドメインで決まる（`site_for()`）。管理表に組織を選ぶ列は
    作らない——人が選ぶ形にすると、URL と食い違ったときに別の組織へ問い合わせて
    「レポートが見つからない」という分かりにくい失敗になる。
    """
    site = site_for(entry.url)
    with site() as salesforce:
        return salesforce.report.run(entry.report_id)


def _save(entry: ReportEntry, rows: list[dict]) -> Path:
    """行数と `allow_empty` に応じて保存先へ書き込み、書き終わったパスを返す。

    0 行・`allow_empty` × → `EmptyReportError`（=失敗）／○ → 空 CSV を置く。
    ヘッダー行は敢えて入れない（Salesforce のメタデータからしか取れず、
    `report.run()` は `list[dict]` 形式を返すため取り出せない）。
    """
    path = file_path_of(entry)
    if not rows:
        # 問い合わせは成功したが明細が無い。**0件あり × なら失敗扱い、○ なら正常終了**
        if not entry.allow_empty:
            raise EmptyReportError(entry.key, entry.summary, entry.url)
        _write_empty_csv(path)
    else:
        _write_csv(path, rows)
    return path


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
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError as e:
            logger.warning("一時ファイルを削除できませんでした: %s（%s）", tmp_path, e)


def _write_empty_csv(path: Path) -> None:
    """0 件のレポート用に、空の CSV ファイルを一時ファイル経由で置く。

    `CsvWriter` はヘッダー行を必須にしているため、0 行のときは直接書く。
    **`_write_csv()` と同じ「一時ファイル→置き換え」の作法**を維持する:
    まとめて一気に入れ替わる／失敗時に残骸を残さない。
    """
    tmp_path = history.new_temp_name(path)
    try:
        # 0 バイトで作成（CSV のほうが BOM 付きなので、空ファイルでも BOM は付けない）
        tmp_path.write_bytes(b"")
        tmp_path.replace(path)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError as e:
            logger.warning("一時ファイルを削除できませんでした: %s（%s）", tmp_path, e)


def _warn_shared_reports(entries: dict[str, ReportEntry]) -> None:
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


def _failure_row(exc: BaseException, seconds: float) -> HistoryRow:
    """失敗時の履歴1行を、**例外の型だけから**組み立てる。

    `fetched` / `saved` は `_download()` の何処で失敗したかを例外で判別する。
    判定順は上から5行（狭い条件から順に評価）:

    1. `ReportFolderNotFoundError` → 取得段階の前（保存先フォルダ検査で停止）
    2. `EmptyReportError` → 取得は成功、保存は未到達（0件 × 一意）
    3. `OSError` → 保存段階（書き込み・権限・共有サーバー断）
    4. その他の `ComkenError` → 取得段階（Salesforce 通信と認証）
    5. それ以外 → プログラム（comken 側の想定外）

    4. は `download_scheduled()` が捕捉する範囲と一致。1か所の判断で
    「握りつぶす範囲」と「履歴側でバグと書く範囲」を揃える。
    """
    if isinstance(exc, ReportFolderNotFoundError):
        fetched, saved, cause = None, None, CAUSE_CONFIG
    elif isinstance(exc, EmptyReportError):
        fetched, saved, cause = True, None, CAUSE_EMPTY_DATA
    elif isinstance(exc, OSError):
        fetched, saved, cause = True, False, CAUSE_FILE
    elif isinstance(exc, ComkenError):
        fetched, saved, cause = False, None, CAUSE_SALESFORCE
    else:
        fetched, saved, cause = False, None, CAUSE_PROGRAM
    return HistoryRow(
        succeeded=False,
        fetched_from_salesforce=fetched,
        saved_to_file=saved,
        seconds=seconds,
        cause=cause,
        error_code=type(exc).__name__,
        error=str(exc),
    )
