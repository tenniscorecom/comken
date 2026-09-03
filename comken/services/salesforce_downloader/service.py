r"""comken/services/salesforce_downloader/service.py — 取得の本体。

    from comken.services.salesforce_downloader import cached_report, download_scheduled

    CUSTOMER_LIST = "1001"        # 各プロジェクトで、意味の分かる名前を付ける

    by_code = cached_report(CUSTOMER_LIST).index("顧客コード")

**2つの関数の意味をはっきり分ける。**

- `download_scheduled()` は「**今この瞬間にまとめて取りに行く**」。管理表で
  `有効` になっているレポートを全て対象に、定期実行のプロジェクトから呼ばれる
- `cached_report()` は「**取っておいたものを受け取る**」。取りに行く関数ではない。
  まだ取れていなければ例外にする。ここで自動的に取りに行くと、**定期取得が動いて
  いないことに誰も気づかなくなる**

戻り値は `Table`。行の検索・抽出・索引化は Table の API でできる。
パスだけ欲しい場合は `cached_report_path()` を使う。
`download_scheduled()` は定期取得したパスのリストを `list[Path]` で返すが、これは
定期取得の呼び出し側が中身を読まず「取らせる」のが目的なので、reader を並べても
使い道がないため（役割の違いが戻り値の型に出ている）。

**急いでその場の最新値が必要なときは、`download_scheduled()` をスケジュール外に
直接実行する。** それ専用のAPIは用意していない。実行タイミングを分ける必要が
あれば、呼び出し側でスケジューラを増やす。Downloader 側に「今すぐ取りに行く」
だけの関数を残すと、定期取得が動いていないことに誰も気づかなくなるため。

プロジェクト側のコードに Salesforce の URL もレポート ID も現れない。管理表の
参照先を差し替えても、`CUSTOMER_LIST = "1001"` はそのままでよい。

このファイルが持つもの:
- 1件を取得して保存し履歴に残す流れ
- Salesforce への問い合わせ

ここに書かないもの:
- 「このプロジェクトのときは」という分岐 → 利用プロジェクト
- スケジュール判定（毎日・平日・月末など）→ 呼び出す側
- 管理表にどんな列があるか → master.py
- 履歴にどんな列があるか → history.py
- Salesforce の認証・API の叩き方 → comken/toolbox/salesforce/
- 取得済みファイルの取り出し（`cached_report` / `file_path_of`）→ provider.py
- 管理表・履歴の置き場所（`MASTER_PATH` / `HISTORY_PATH`）→ _paths.py
- 管理表から1行を引く `_find()` → provider.py（`requests` を経由しない側に置く）
"""

import datetime as dt
import logging
import shutil
import time
from pathlib import Path

from comken.core.clock import now as clock_now
from comken.core.files import atomic_write
from comken.core.holidays import default_calendar
from comken.core.table.model import Table
from comken.core.timer import measure
from comken.exceptions import (
    ComkenError,
    EmptyReportError,
    HistoryHeaderMismatchError,
    HistoryLockTimeoutError,
    HistoryWriteError,
    ReportFolderNotFoundError,
    ReportReservePathLimitError,
    ScheduledDownloadFailedError,
)
from comken.services.salesforce_downloader import history
from comken.services.salesforce_downloader._paths import (
    HISTORY_PATH,
    LATEST_STATUS_PATH,
    MASTER_PATH,
)
from comken.services.salesforce_downloader.history import HistoryRow
from comken.services.salesforce_downloader.latest_status import write_latest_status
from comken.services.salesforce_downloader.master import (
    ReportEntry,
    load_master,
    shared_report_ids,
)
from comken.services.salesforce_downloader.provider import _daily_cache_path_of, file_path_of
from comken.services.salesforce_downloader.schedule import ScheduleRule, load_schedule
from comken.toolbox.csv import CSV
from comken.toolbox.salesforce.sites import site_for

logger = logging.getLogger(__name__)

# 履歴の「原因区分」列に出す5値。運用する人が履歴からすぐ「誰が動くか」を判断できるように、
# 抽象クラス名ではなく誰が直すかで分ける（設計判断は docs/開発/仕様書.md 4.28 参照）
CAUSE_CONFIG = "設定"
CAUSE_SALESFORCE = "Salesforce"
CAUSE_EMPTY_DATA = "データなし"
CAUSE_FILE = "ファイル"
CAUSE_PROGRAM = "プログラム"

# ``_reserve_path`` が連番を足して空きファイル名を探索する回数の上限。
# ``comken.core.holidays.calendar.BUSINESS_DAY_SEARCH_LIMIT`` と同じ理由で、
# 共有サーバーの同期・権限異常などで ``FileExistsError`` が返り続けると無限
# ループになるため、必ず上限を切る。
RESERVE_PATH_LIMIT = 1000


@measure
def download_scheduled(project: str = "定期実行") -> list[Path]:
    """管理表で有効なレポートをまとめて取得する。

    定期実行のプロジェクトから呼ぶ。**1件失敗しても残りは続ける**。戻り値は `list[Path]`
    のままで `CSV` を返さない（定期取得の呼び出し側は中身を読まないため）。

    **「スケジュール」シート**にこのレポートの行が無いときは、
    「有効」だけで毎回対象にする（後方互換）。
    この機能追加を境に既存のレポートが突然取得されなくなる事故を防ぐため。

    Raises:
        ScheduledDownloadFailedError: 1件でも取得できなかった場合。**取得できたものは
            保存したうえで**送出する。ログだけに出して正常終了すると、スケジューラや
            RPA 基盤から見て成功と区別が付かない。
    """
    entries = load_master(MASTER_PATH)
    _warn_shared_reports(entries)

    # スケジュール管理表を読んで、レポートキーで引けるように索引化。**有効行だけ**を
    # 評価対象にする（無効行は曜日・時刻を足切りする材料にならない）。
    # シートが無い場合は空リスト（後方互換）
    schedule_rules = load_schedule(MASTER_PATH)
    rules_by_report: dict[str, list[ScheduleRule]] = {}
    for rule in schedule_rules:
        if rule.enabled:
            rules_by_report.setdefault(rule.report_key, []).append(rule)

    current = clock_now()
    # 祝日は「今日が祝日か」だけ分かればよいので、1日分の set を作る
    holidays = _todays_holiday_set(current)

    targets: list[tuple[ReportEntry, str]] = []
    for entry in entries.values():
        if not entry.enabled:
            continue
        is_due, schedule_key = _matched_schedule_key(entry, rules_by_report, current, holidays)
        if is_due:
            # ``schedule_key`` は取得後に履歴へ記録し、``schedule_succeeded_today()``
            # が再判定に使う。スケジュール行が無いレポート（後方互換）は空文字
            targets.append((entry, schedule_key))
    logger.info("定期取得の対象: %d 件", len(targets))

    saved: list[Path] = []
    failed: list[str] = []
    # 失敗時に ``ScheduledDownloadFailedError`` から ``__cause__`` で辿れるよう、
    # 直近の捕捉した例外を覚えておく（同じ失敗が複数件あっても、最後の1件だけを
    # 連鎖させる）。``None`` のままだと「原因例外が無い」ことを示す
    last_exception: BaseException | None = None
    for entry, schedule_key in targets:
        try:
            saved.append(_download(entry, project, HISTORY_PATH, schedule_key))
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
            #   どちらでもないので、これもそのまま抜ける
            logger.error("取得に失敗しました: %s（%s）", entry.key, e)
            failed.append(entry.key)
            last_exception = e

    logger.info("定期取得: %d 件中 %d 件を取得しました。", len(targets), len(saved))
    # **最新ステータスは別ファイルへ上書きする。** 履歴 CSV は「全実行の記録」で
    # 1 レポートの最新だけ見たい業務側からは探しにくいので、``download_scheduled()``
    # のたびに管理表 × 履歴の最新行を 1 シートへまとめる。失敗しても定期取得の
    # 成否判定には影響させない（``ScheduledDownloadFailedError`` は本体結果で決まる）
    try:
        write_latest_status(
            master_path=MASTER_PATH,
            history_path=HISTORY_PATH,
            output_path=LATEST_STATUS_PATH,
        )
    except Exception as e:
        logger.warning("最新ステータスの更新に失敗しました（定期取得は本体の結果で判定）: %s", e)
    if failed:
        # 続けたぶん、最後に必ず知らせる（終了コードで落ちたことが分かるように）。
        # 直近の失敗を ``__cause__`` に乗せて送出する（呼び出し側が
        # ``raise X from original`` 相当の診断情報を得られるようにする）
        raise ScheduledDownloadFailedError(failed, HISTORY_PATH) from last_exception
    return saved


class _Attempt:
    """1件の取得（フォルダ確認 → 取得 → 保存）を取り持つ文脈。

    履歴を書く関数に毎回同じ値の組を渡す煩雑さを消すための箱。
    コンストラクタで文脈を1回だけ受け取り、開始時刻もここで `time.perf_counter()`
    で記録する。`record_*()` は履歴とログを書くだけ。`_download()` 側の
    `try/except` はそのまま（失敗の段階と原因区分は `_failure_row()` が
    例外の型だけから決める）。

    履歴の「実行方式」列は **固定で `TRIGGER_SCHEDULED`**（=`定期`）になった。
    `download_scheduled()` しか残っていないので、トリガは1値しか取らない。
    引数で渡さずクラス内で固定することで、``_download`` のシグネチャを簡略化した
    （1値しか渡らない引数を残すのはYAGNI違反）。

    ``schedule_key`` はスケジュール行に紐付く取得で値が入り、スケジュール行が無い
    レポートの取得（後方互換）は空文字。``_matched_schedule_key()`` が
    戻り値の第2要素として返した値をそのまま受け取り、``HistoryRow.schedule_key``
    に詰めて履歴へ書く。
    """

    def __init__(
        self, entry: ReportEntry, project: str, history_path: Path, schedule_key: str = ""
    ) -> None:
        self._entry = entry
        self._project = project
        self._history_path = history_path
        self._schedule_key = schedule_key
        self._started = time.perf_counter()

    def record_failure(self, exc: BaseException) -> None:
        """失敗時の履歴とログ。"""
        row = _failure_row(
            exc,
            time.perf_counter() - self._started,
            schedule_key=self._schedule_key,
        )
        # 値を計算した場所（ここ）で、ログにも書く。`_download()` 抜けたあと
        # 別の層で「同じ値」を再利用することはない（後付けで属性を渡さない）
        logger.error("取得に失敗しました: %s（%s / 区分=%s）", self._entry.key, exc, row.cause)
        history.record(
            self._history_path,
            entry=self._entry,
            project=self._project,
            row=row,
        )

    def record_success(self, path: Path, rows: Table) -> None:
        """成功時の履歴とログ。"""
        seconds = time.perf_counter() - self._started
        row = HistoryRow(
            succeeded=True,
            fetched_from_salesforce=True,
            saved_to_file=True,
            file_name=path.name,
            row_count=len(rows),
            seconds=seconds,
            schedule_key=self._schedule_key,
        )
        if rows:
            logger.info("取得しました: %s（%d 行 / %.1f 秒）", path, len(rows), seconds)
        else:
            logger.info("取得しました: %s（0 件 / 0件ありのため正常）", path)
        history.record(
            self._history_path,
            entry=self._entry,
            project=self._project,
            row=row,
        )


def _download(
    entry: ReportEntry,
    project: str,
    history_path: Path,
    schedule_key: str = "",
) -> Path:
    """1件を取得して保存し、成否を履歴に残す。"""
    attempt = _Attempt(entry, project, history_path, schedule_key)
    try:
        _require_folder(entry)
        table = _fetch(entry)
        path = _save(entry, table)
        _update_daily_cache(entry, path)
    except Exception as exc:
        try:
            attempt.record_failure(exc)
        except (
            HistoryWriteError,
            HistoryLockTimeoutError,
            HistoryHeaderMismatchError,
        ) as history_exc:
            # 元の取得失敗 (`exc`) を ``__cause__`` に乗せて送出する。
            # 履歴書込み失敗の ``history_exc`` はメッセージに含めて、
            # ``ScheduledDownloadFailedError`` の連鎖には元の失敗を
            # 残す（`raise X from history_exc` だと ``history_exc`` が
            # ``__cause__`` を埋めて元の失敗が辿れなくなる）
            raise HistoryWriteError(history_path, str(history_exc), original=exc) from exc
        raise
    attempt.record_success(path, table)
    return path


def _require_folder(entry: ReportEntry) -> None:
    """保存先フォルダが無ければ `ReportFolderNotFoundError`。**勝手に作らない。**

    作らずに失敗させる。無いのは書き間違いのことが多く、勝手に作ると
    誰も読まない場所へ置き続けることになる。
    """
    if not entry.folder.is_dir():
        raise ReportFolderNotFoundError(entry.key, entry.folder)


def _fetch(entry: ReportEntry) -> Table:
    """Salesforce へ問い合わせて明細表を返す。

    つなぐ組織は URL のドメインで決まる（`site_for()`）。管理表に組織を選ぶ列は
    作らない——人が選ぶ形にすると、URL と食い違ったときに別の組織へ問い合わせて
    「レポートが見つからない」という分かりにくい失敗になる。
    """
    site = site_for(entry.url)
    with site() as salesforce:
        return salesforce.report.get(entry.report_id)


def _save(entry: ReportEntry, table: Table) -> Path:
    """行数と `allow_empty` に応じて保存先へ書き込み、書き終わったパスを返す。

    0 行・`allow_empty` × → `EmptyReportError`（=失敗）／○ → 空 CSV を置く。
    ``report.get()`` が返す ``Table.columns`` を使うため、0 行でも Salesforce の
    メタデータから得た見出しを保存する。
    """
    path = _reserve_path(entry)
    try:
        # 問い合わせは成功したが明細が無い。**0件あり × なら失敗扱い、○ なら正常終了**
        if not table and not entry.allow_empty:
            raise EmptyReportError(entry.key, entry.summary, entry.url)
        _write_csv(path, table)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def _reserve_path(entry: ReportEntry) -> Path:
    """排他的な新規作成で保存名を予約し、既存ファイルを上書きしない。

    同じフォルダに既存ファイルがあると連番（ ``_1`` / ``_2`` …）を足して別の
    ファイル名を探す。 ``RESERVE_PATH_LIMIT`` を超えると ``ReportReservePathLimitError``
    を送出する（権限・同期の異常で ``FileExistsError`` が返り続ける無限ループを
    避けるため）。 ``BUSINESS_DAY_SEARCH_LIMIT`` と同じ考え方で上限を切っている。
    """
    base_path = file_path_of(entry)
    candidate = base_path
    sequence = 0
    for _ in range(RESERVE_PATH_LIMIT):
        try:
            candidate.open("x").close()
            return candidate
        except FileExistsError:
            sequence += 1
            candidate = base_path.with_stem(f"{base_path.stem}_{sequence}")
    raise ReportReservePathLimitError(entry.key, base_path, RESERVE_PATH_LIMIT)


def _update_daily_cache(entry: ReportEntry, saved_path: Path) -> None:
    """時刻付き保管ファイルを残したまま、当日最新キャッシュを原子的に更新する。"""
    cache_path = _daily_cache_path_of(entry)
    with atomic_write(cache_path) as temporary_path:
        # レポート全体をメモリへ読み込むと、大きなCSVでメモリ不足になりうる。
        # ファイル同士をストリームコピーし、書き終わったあとでatomicに入れ替える。
        shutil.copyfile(saved_path, temporary_path)


def _write_csv(path: Path, table: Table) -> None:
    """一時ファイルへ書いてから置き換える。

    複数のプロジェクトが同時に呼ぶので、直接書くと**読んでいる最中のファイルが
    半端な状態**になりうる。同じフォルダ内の置き換えは一度に入れ替わる。
    """
    with atomic_write(path) as tmp, CSV(tmp) as csv_file:
        csv_file.replace(table)


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


def _matched_schedule_key(
    entry: ReportEntry,
    rules_by_report: dict[str, list[ScheduleRule]],
    current: dt.datetime,
    holidays: set[dt.date],
) -> tuple[bool, str]:
    """このレポートを今取得すべきか、すべきなら根拠のスケジュールキーを返す。

    戻り値は ``(取得すべきか, スケジュールキー)``。スケジュールキーは、
    取得すべきだった場合に「どのスケジュール行が根拠になったか」を表し、
    履歴の ``スケジュールキー`` 列にそのまま記録する。スケジュール行が無い
    レポート（後方互換）の取得時は空文字を返す。

    判定ロジック:

    - スケジュール行が無いレポートは ``downloaded_today()`` ベースで「今日まだ
      取れていなければ」取得（後方互換）
    - スケジュール行がある場合、いずれかの行が ``is_due()`` True で、かつ
      ``schedule_succeeded_today()`` が False（=今日まだ成功していない）なら取得。
      複数の行が True を返す場合は取得時刻が一番遅い行のキーを採用（それより早い
      時刻の行は無視する）。``run_time is None`` の行は最も早い扱いとし、具体的な
      時刻を持つ行がある限りそちらを優先する
    - いずれの行も ``is_due()`` False なら False, ""
    - いずれかの行が ``is_due()`` True でも、今日すでに成功済みなら False, ""
    """
    rules = rules_by_report.get(entry.key)
    if not rules:
        # スケジュール行が無いレポート: ``downloaded_today()`` で 1 日 1 回までに
        # 制限する（後方互換）。戻り値のキーは空文字
        return not history.downloaded_today(HISTORY_PATH, entry.key), ""
    due_rules = [
        rule
        for rule in rules
        if rule.is_due(current, holidays=holidays)
        and not history.schedule_succeeded_today(HISTORY_PATH, rule.schedule_key)
    ]
    if not due_rules:
        return False, ""
    # ``run_time is None`` の行は具体的な時刻より優先度が低い（時刻条件なしの行で
    # 取得すると、後の時刻の行を再評価する余地がなくなるため）。
    latest = max(due_rules, key=lambda rule: rule.run_time or dt.time.min)
    return True, latest.schedule_key


def _todays_holiday_set(current: dt.datetime) -> set[dt.date]:
    """今日が祝日なら {今日}、そうでなければ空集合を返す。

    ``is_due()`` の祝日スキップ判定は「対象日が holidays に含まれるか」だけ見る
    ので、期間を取って集合化する必要は無く、当日1日分だけ用意すれば十分
    （1日分の判定にしか使わないため。``ScheduleRule.is_due`` の引数を
    整えた実装詳細）。
    """
    return {current.date()} if default_calendar().is_holiday(current.date()) else set()


def _failure_row(exc: BaseException, seconds: float, schedule_key: str = "") -> HistoryRow:
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

    `schedule_key` は成功時と同じく履歴の「スケジュールキー」列へ書くためのもの。
    dedup 判定は成功行しか見ないが、履歴を後から追ったときに「どのスケジュール行が
    いつ失敗したか」が追えるよう、`record_success()` と対称にここで渡す
    （後方互換のため既定値は空文字）。
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
        schedule_key=schedule_key,
    )
