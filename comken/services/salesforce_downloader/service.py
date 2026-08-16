r"""comken/services/salesforce_downloader/service.py — 取得の本体。

    from comken.services.salesforce_downloader import download_report, get_scheduled_report

    CUSTOMER_LIST = 1001          # 各プロジェクトで、意味の分かる名前を付ける

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
参照先を差し替えても、`CUSTOMER_LIST = 1001` はそのままでよい。

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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ...core.files import DateNameBuilder
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
from ...toolbox.csv import CsvReader, CsvWriter
from ...toolbox.salesforce.sites import site_for
from . import history
from .master import ReportEntry, load_master, shared_report_ids

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

# 並列で定期取得するときのワーカー数。**`MAX_BACKGROUND_TASKS` のように呼び出し側から
# 渡せない形にする**——プロジェクトごとに値が違うと、共有サーバー上で複数プロジェクトが
# 同時に走ったときに「合計で Salesforce の API 枠を誰がどれくらい食っているか」が
# 追えなくなるため。値はライブラリ側で固定する。
# 4 にした理由:
# - ブラウザ側の `_MAX_BACKGROUND_TASKS = 16` と違って、**相手（Salesforce）の
#   API 実行枠を消費する**側。1ターンに 4 本までなら、レート制限に当たりにくく、
#   当たってもリトライで吸収できる経験的な値
# - 共有サーバー上で複数のプロジェクトが並列で呼びうるので、**1プロジェクトが
#   食える量を絞る**。プロジェクト側が勝手に上限を上げると合計で枠を食い尽くす
# - 待ち時間のほとんどは Salesforce との通信（I/O）で CPU をほぼ使わないので、
#   Python の GIL が並列度の制約にはならない。スレッドで十分
MAX_WORKERS = 4


def download_report(report_key: int, project: str = "") -> CsvReader:
    """今すぐ Salesforce から取得して保存し、そのファイルを `CsvReader` で返す。

    **必ず Salesforce へ問い合わせる。** 今日すでに取っていても取り直す。

    Args:
        report_key: 管理表の管理番号（例: 1001）。
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


def get_scheduled_report(report_key: int, project: str = "") -> CsvReader:
    """定期取得しておいたファイルを `CsvReader` で返す。**取りに行かない。**

    Args:
        report_key: 管理表の管理番号（例: 1001）。
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

    定期実行のプロジェクトから呼ぶ。**1件失敗しても残りは続ける** ——
    5本のうち1本が落ちたときに全部やり直すと、手で用意する手間が5本ぶんになる。

    `MAX_WORKERS` 本のワーカーで並列に走らせる（並列度の理由は定数のコメント参照）。
    **全件の完了を待ってから**失敗を判定する（途中では止めない）。並列で走らせても、
    出力の順序は管理表の順を保つ。完了順だと実行のたびに並びが変わり、ログ・履歴・
    戻り値を目視で比べられなくなるため。

    戻り値は `list[Path]` のままで **`CsvReader` を返さない**。定期取得の呼び出し側は
    中身を読まず「取らせる」のが目的なので、reader を並べても使い道がないため
    （役割の違いが戻り値の型に出ている）。

    Args:
        project: 履歴に残す呼び出し元の名前。

    Returns:
        取得できたファイルのパス。**管理表の順に並んだ** `list[Path]`。

    Raises:
        ScheduledDownloadFailedError: 想定内の失敗（`ComkenError` / `OSError`）が
            1件以上あった場合。**取得できたものは保存したうえで**送出する。
            ログだけに出して正常終了すると、スケジューラや RPA 基盤から見て成功と
            区別が付かないため。`failed` には**管理表の順**で管理番号が入る。
        Exception: 想定外の例外（`TypeError` など、comken 側のバグ）が1件でもあった
            場合、**全件の完了を待ってから**管理表順で最初のものをそのまま送出する。
            `ScheduledDownloadFailedError` の顔で出さないのは逐次版と同じ意図
            ——非エンジニアが「もう一度実行してみる」を繰り返すだけになるため。
            成功した他のレポートは保存済みであることに変わりはない。
    """
    entries = load_master(MASTER_PATH)
    _warn_shared_reports(entries)

    targets = [entry for entry in entries.values() if entry.is_scheduled and entry.enabled]
    logger.info("定期取得の対象: %d 件", len(targets))

    # 全部の完了を待ってから失敗を判定する。逐次版と違い、**想定外例外もここでは
    # 送出してしまわない**——投入済みのタスクを途中で打ち切っても、走り出した
    # Salesforce への問い合わせは止まらず、履歴だけが中途半端に残るため。
    # 順序を管理表順に揃える理由と方法は `_run_parallel()` 側に書いてある
    saved, failed, unexpected_errors = _run_parallel(targets, project, history.TRIGGER_SCHEDULED)

    # 想定外はログに出したうえで、管理表順で最初のものをそのまま送出する。
    # `ScheduledDownloadFailedError` の顔で出さないのは逐次版と同じ意図——
    # 非エンジニアが「もう一度実行してみる」を繰り返すだけになるため。
    # **ここで全件ログを出す理由**: 並列版では「想定外が複数件あっても、
    # 送出できるのは管理表順で最初の 1 件だけ」。2 件目以降の例外はここで
    # ログに残さない限りどこにも残らないため、`download_scheduled()` 側で
    # 全件を 1 行ずつ書き出す
    for key, exc in unexpected_errors:
        logger.error("取得に失敗しました: %s（%s）", key, exc)
    if unexpected_errors:
        raise unexpected_errors[0][1]

    logger.info("定期取得: %d 件中 %d 件を取得しました。", len(targets), len(saved))
    if failed:
        # 続けたぶん、最後に必ず知らせる（終了コードで落ちたことが分かるように）。
        # `failed` の並びは管理表順（投入順に `result()` を取り、`failed.append()` の
        # 順番をそのまま使うため）
        raise ScheduledDownloadFailedError(failed, HISTORY_PATH)
    return saved


def _run_parallel(
    targets: list[ReportEntry],
    project: str,
    trigger: str,
) -> tuple[list[Path], list[int], list[tuple[int, Exception]]]:
    """`targets` を並列に走らせ、3 つの結果に分けて返す。

    - `saved`: 保存できたパス。**管理表順**（投入順に `result()` を取り、
      `append()` の順番をそのまま使うため）
    - `failed`: 想定内の失敗（`ComkenError` / `OSError`）の管理番号。
      **管理表順**（同上）
    - `unexpected_errors`: 想定外の例外（バグ）。**(管理番号, 例外)** の組を
      **管理表順**で入れる。呼び出し側がここで先頭のものをそのまま送出する
      ——`ScheduledDownloadFailedError` の顔で出さないのは逐次版と同じ意図

    **Future の例外機構をそのまま使う設計**: `_run_one()` は `Path | None` を
    返すだけにし、想定外例外は Future 内に保持させる。呼び出し側の
    `future.result()` で再送出されたものをそのまま受け取る方が、戻り値タプルで
    受け取って `try / except` で詰め替えるより**情報が落ちない**（呼び出し側の
    スタックフレームを保ったまま伝搬し、`__traceback__` もそのまま）。想定内の
    失敗（`ComkenError` / `OSError`）は `_download()` 側で履歴・ログまで書いた
    うえで `None` を返す扱いにする。

    並列度の定数はモジュール定数 `MAX_WORKERS` で固定する（呼び出し側に渡さない）。
    """
    saved: list[Path] = []
    failed: list[int] = []
    unexpected_errors: list[tuple[int, Exception]] = []

    def _run_one(entry: ReportEntry) -> Path | None:
        """1 件分の処理。成功時は `Path`、想定内の失敗は `None`、想定外は送出する。

        想定内の失敗（`ComkenError` / `OSError`）は `_download()` 内で履歴に書いた
        うえでログだけ出して `None` を返す。想定外（バグ）は捕捉しない——
        Future に持たせて `future.result()` で再送出される方が、情報を落とさず
        に済むため
        """
        try:
            return _download(entry, project, trigger, HISTORY_PATH)
        except (ComkenError, OSError) as e:
            # 想定した失敗（共有サーバー・権限・通信・0 件・フォルダ無し 等）。
            # `_download()` 側で既に履歴・ログを書いているので、ここでは「続行する
            # 対象」として記録するだけ。追加で1行ログを出しているのは、逐次版と
            # 同じ運用上のメッセージを保つため
            logger.error("取得に失敗しました: %s（%s）", entry.key, e)
            return None

    # **KeyboardInterrupt の挙動**: `ThreadPoolExecutor.__exit__` は
    # `shutdown(wait=True)` 相当のため、Ctrl+C があっても**実行中タスクの
    # 完了を待ち、キューに残った未開始タスクもすべて起動してから**メインスレッド
    # へ `KeyboardInterrupt` を伝搬する。逐次版は「Ctrl+C でその場で抜けていた」
    # のと挙動が違うが、定期実行はスケジューラから無人で起動するもので、人が
    # Ctrl+C する場面が運用にないため打ち切りの仕組みは入れていない
    # （実行中に人が止める必要が出た時点で運用設計の問題なので、分岐を足さない）
    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS, thread_name_prefix="sf-downloader"
    ) as executor:
        # `targets` の順（=管理表順）に `result()` を取り、append 順を管理表順に
        # 揃える。`as_completed()` を使うと完了順になり、`saved` / `failed` の
        # 並びが実行ごとに変わってしまう
        futures = [executor.submit(_run_one, entry) for entry in targets]
        for entry, future in zip(targets, futures, strict=True):
            try:
                path = future.result()
            except Exception as e:
                # 想定外（バグ）。Future に持たせていたものが再送出される
                unexpected_errors.append((entry.key, e))
                continue
            if path is not None:
                saved.append(path)
            else:
                failed.append(entry.key)
    return saved, failed, unexpected_errors


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
    """1件を取得して保存し、成否を履歴に残す。

    履歴の各段階（Salesforce への問い合わせ、保存）は別々に書き出す。
    0 行のとき `Salesforce取得結果 = 成功` になるのが要点で、
    **Salesforce との通信は成功していて、レポートの中身が空だった**ことを
    区別できるようにするため（4. の表を参照）。
    """
    path = file_path_of(entry)
    started = time.perf_counter()
    # 各段階の結果を組み立ててから履歴を書く。途中で例外になっても、どこまで
    # 進んだかが履歴に残る
    fetched_from_salesforce: bool | None = None
    saved_to_file: bool | None = None
    rows: list[dict] = []
    try:
        if not entry.folder.is_dir():
            # 作らずに失敗させる。無いのは書き間違いのことが多く、勝手に作ると
            # 誰も読まない場所へ置き続けることになる
            raise ReportFolderNotFoundError(entry.key, entry.folder)

        try:
            rows = _fetch(entry)
        except Exception:
            fetched_from_salesforce = False
            raise
        fetched_from_salesforce = True
        if not rows:
            # 問い合わせは成功したが明細が無い。**0件あり × なら失敗扱い、○ なら正常終了**
            if not entry.allow_empty:
                raise EmptyReportError(entry.key, entry.summary, entry.url)
            # 0件あり ○ のとき: 空の CSV を置く。`CsvReader` は 0 バイトでも例外に
            # ならず `read_rows() == []` を返すので、利用側は 0 件を自然に扱える
            # （salesforce-downloader.md の「0 件の扱い」節参照）。
            # ヘッダー行は敢えて入れない（Salesforce のメタデータからしか取れず、
            # `report.run()` は `list[dict]` 形式を返すため取り出せない）。
            # 一時ファイル経由の置き換えは `_write_csv()` と同じ作法を踏襲する
            try:
                _write_empty_csv(path)
            except Exception:
                saved_to_file = False
                raise
            saved_to_file = True
        else:
            try:
                _write_csv(path, rows)
            except Exception:
                saved_to_file = False
                raise
            saved_to_file = True
    except Exception as e:
        cause = _classify_cause(e, fetched_from_salesforce, saved_to_file)
        history.record(
            history_path,
            report_key=entry.key,
            summary=entry.summary,
            report_id=entry.report_id,
            url=entry.url,
            project=project,
            trigger=trigger,
            succeeded=False,
            fetched_from_salesforce=fetched_from_salesforce,
            saved_to_file=saved_to_file,
            folder=entry.folder,
            seconds=time.perf_counter() - started,
            cause=cause,
            error_code=type(e).__name__,
            error=str(e),
        )
        # 値を計算した場所（ここ）で、ログにも書く。`_download()` を抜けたあと
        # 別の層で「同じ値」を再利用することはない（後付けで属性を渡さない）
        logger.error("取得に失敗しました: %s（%s / 区分=%s）", entry.key, e, cause)
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
        fetched_from_salesforce=fetched_from_salesforce,
        saved_to_file=saved_to_file,
        folder=entry.folder,
        file_name=path.name,
        row_count=len(rows),
        seconds=seconds,
        cause="",
    )
    if rows:
        logger.info("取得しました: %s（%d 行 / %.1f 秒）", path, len(rows), seconds)
    else:
        logger.info("取得しました: %s（0 件 / 0件ありのため正常）", path)
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
        try:
            tmp_path.unlink(missing_ok=True)  # 途中で失敗したときに残骸を残さない
        except OSError as e:
            # 後始末の失敗で、取得・保存時に起きた本来の例外を上書きしない
            logger.warning("一時ファイルを削除できませんでした: %s（%s）", tmp_path, e)


def _write_empty_csv(path: Path) -> None:
    """0 件のレポート用に、空の CSV ファイルを一時ファイル経由で置く。

    `CsvWriter` はヘッダー行を必須にしているため、0 行のときは直接書く。
    **`_write_csv()` と同じ「一時ファイル→置き換え」の作法**を維持する:
    - 同時に走っても読んでいる側のファイルが半端な状態にならない
    - 途中で失敗したら一時ファイルを残さない（`finally` で削除）
    """
    tmp_path = history.new_temp_name(path)
    try:
        # 0 バイトで作成（encoding は CsvWriter と同じ UTF-8 BOM 付きで揃える。
        # 空ファイルなので中身は無いが、BOM だけ書くと後続の CsvReader で
        # 1文字目の判定が面倒になるため、書かない）
        tmp_path.write_bytes(b"")
        tmp_path.replace(path)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError as e:
            logger.warning("一時ファイルを削除できませんでした: %s（%s）", tmp_path, e)


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


# 履歴の「原因区分」列に出す5値。運用する人が履歴からすぐ「誰が動くか」を判断できるように、
# 抽象クラス名ではなく誰が直すかで分ける（設計判断は docs/仕様書.md 4.28 参照）
CAUSE_CONFIG = "設定"
CAUSE_SALESFORCE = "Salesforce"
CAUSE_EMPTY_DATA = "データなし"
CAUSE_FILE = "ファイル"
CAUSE_PROGRAM = "プログラム"


def _classify_cause(
    error: BaseException,
    fetched_from_salesforce: bool | None,
    saved_to_file: bool | None,
) -> str:
    """失敗の原因区分を、例外と「どこまで進んだか」だけから決める。

    **例外クラス名との対応表を持たない。** 例外を増やすたびに更新漏れが起き、
    `ERRORS.md` と二重管理になる。代わりに、履歴に残している3状態
    (`fetched_from_salesforce` / `saved_to_file`) と例外の種類だけから機械的に決める
    （上から順に評価する5行）。

    1. `ComkenError` でも `OSError` でもない → **`プログラム`**（comken 側の想定外＝バグ）
    2. 保存段階で落ちた（`saved_to_file` が `False`）→ **`ファイル`**（共有サーバー・権限）
    3. **取得は成功したが保存に進まなかった（`fetched_from_salesforce` が `True` かつ
       `saved_to_file` が `None`）→ `データなし`**
       （「0件あり が × なのに 0 行だった」一意。理由は下コメント参照）
    4. 取得段階で落ちた（`fetched_from_salesforce` が `False`）→ **`Salesforce`**
       （問い合わせ・通信の失敗）
    5. それ以外（取得段階に入る前に落ちた）→ **`設定`**（管理表の書き方や保存先フォルダ）

    **3 が 0 件を一意に指す理由**: 取得成功（`fetched_from_salesforce = True`）を
    確定させてから保存の `try` に入るまでの間に発生しうる例外は `EmptyReportError`
    だけ。`EmptyReportError` は保存の `try` を開く**前**に `raise` されるため、
    この経路で `saved_to_file` は必ず `None` のままである（保存段階に到達していない
    から `False` になりようがない）。
    つまり `True + None` という組合せは 0 件失敗しか取り得ず、例外クラス名を書かずに
    段階だけで特定できる。

    1. の条件は `download_scheduled()` が捕捉しない例外と**まったく同じ**で、
    「ダウンロード側で握りつぶす範囲」と「履歴側で『バグ』と書く範囲」を1か所の判断で
    一致させている。2箇所で別々に書かないための対応関係。
    """
    if not isinstance(error, (ComkenError, OSError)):
        return CAUSE_PROGRAM
    if saved_to_file is False:
        return CAUSE_FILE
    if fetched_from_salesforce is True and saved_to_file is None:
        return CAUSE_EMPTY_DATA
    if fetched_from_salesforce is False:
        return CAUSE_SALESFORCE
    return CAUSE_CONFIG
