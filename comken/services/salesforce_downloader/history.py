"""comken/services/salesforce_downloader/history.py — 履歴CSVの列と、読み取り・書き込み。

**`sheets/` には、ワークブック・CSVの「1枚（1ファイル）」ごとに、そこにある列と
意味を宣言するモジュールを集めていたが、2026-09 に管理表・スケジュール・
設定・SOQL 関連が comken の外（Salesforceレポートダウンローダー）へ移ったので、
`history.py` を 1 段上へ出した。** ここに残っているのは「履歴CSVの列・1行の形
（`COLUMNS` / `HistoryRow`）」と、「その形式で書かれた履歴の読み取り関数と、
管理番号だけで取得済みレポートを引く読み取り関数」、および「ダウンローダーが
記録する 1 行を追記する `append_history()`」だけ。

**履歴は取得実行側（Salesforceレポートダウンローダー側）と comken 側の両方が
同じ形式で読み書きする共有契約。** `COLUMNS` / `HistoryRow` / `HistoryFileLock`
（`history_file_lock.py`）を両方が import して使うので、列やロックの取り方が
2 箇所で食い違う事故を防いでいる。

**管理表とは別のファイルにする。** 書く主体が違う（管理表は人、履歴はプログラム）ので
分けないと、人が開いている間にプログラムが保存できず履歴が飛ぶ。**CSV に追記する。**
複数のプロジェクトが同時に走るので、Excel を開いて保存し直す方式だと壊れる。

読み取り・書き込みどちらも comken 自前の ``CSV`` クラス（``comken.toolbox.csv.CSV``）
に委譲する。文字コード自動判定・見出しの検証（空・重複）は ``CSV`` が行うので、
読み取りは「ロックを掛けて ``CSV`` で読み、行を ``migrate_row()`` で揃える」だけ、
書き込みは「ロックを掛けて ``CSV`` で ``read`` → マイグレーション or そのまま追記
→ ``replace`` で1回書き直し」を繰り返す。
"""

import datetime
import datetime as dt
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from comken.core.dates import now, today
from comken.core.table import Table
from comken.core.timer import measure
from comken.exceptions import InvalidTableInputError, ReportNotDownloadedError
from comken.services.salesforce_downloader.history_file_lock import HistoryFileLock
from comken.toolbox.csv import CSV

logger = logging.getLogger(__name__)

# 履歴CSVの列。順序は出力ファイルそのものなので、追加・並び替えは全プロジェクトの
# 既存履歴を読む処理へ影響する（互換性ポリシーに従う）
COLUMNS: tuple[str, ...] = (
    "実行日時",
    "管理番号",
    # スケジュール行に紐付く取得を記録するキー。スケジュール行が無いレポートの
    # 取得（後方互換）は空文字。``schedule_succeeded_today()`` がこの列を見て
    # 「同じスケジュール行を今日すでに実行したか」を判定する
    "スケジュールキー",
    "概要",
    "レポートID",
    "URL",
    "プロジェクト",
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

# 履歴のトリガ。`download_scheduled()` しか残っていないので、`定期` 1 値だけ。
# 互換のため名前は残してある（外部ツールが定数名参照に備えて）
TRIGGER_SCHEDULED = "定期"

# 2000件超で失敗したときの例外クラス名。書き込み側が `error_code=type(exc).__name__`
# で例外クラス名を履歴に書くため、比較対象も同じ文字列にする。``history.py`` は
# Salesforce の例外クラスを import しない（依存を増やさない）ので、import せず
# 文字列リテラルで扱う
TRUNCATED_ERROR_NAME = "SalesforceReportTruncatedError"

_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True)
class HistoryRow:
    """履歴1行の「呼び出し側が組み立てる部分」。履歴の列と1対1。

    `fetched_from_salesforce` / `saved_to_file` は `True` / `False` / `None` の3状態で、
    未到達は `None`。`schedule_key` はスケジュール行に紐付く取得で値が入り、
    スケジュール行が無いレポートの取得（後方互換）は空文字。

    `append_history()` を直接書く用途でも、書き込み側（Salesforceレポートダウン
    ローダー）が `ReportEntry` から組み立てた値を `Mapping` で渡す流儀をサポート
    するため、公開は残す（フィールド名は呼び出し側の組み立てに依らない）。
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
    schedule_key: str = ""


# ── 読み取り ────────────────────────────────────────────────────────────
@measure
def downloaded_today(
    path: str | Path,
    report_key: str,
    trigger: str = TRIGGER_SCHEDULED,
    date: datetime.date | None = None,
) -> bool:
    """その日の取得が成功しているかを履歴から調べる。

    **ファイルの有無ではなく履歴で判定する。** 保存先に今日の日付のファイルがあっても、
    それが定期取得で置かれたのか、手で置いたのかは分からない。
    「定期取得が動いているか」を知りたいので、履歴を正とする。

    Args:
        path: 履歴 CSV のパス。
        report_key: 管理番号。
        trigger: 互換のために残した引数（既定は定期）。`download_scheduled()` 1 本に
            なった現在、トリガは事実上1値。
        date: 調べる日付。省略すると今日。

    Returns:
        その日に成功した記録があれば True。履歴が無ければ False。
    """
    path = Path(path)
    return bool(successful_files_today(path, report_key, trigger, date))


@measure
def successful_files_today(
    path: str | Path,
    report_key: str,
    trigger: str = TRIGGER_SCHEDULED,
    date: datetime.date | None = None,
) -> list[Path]:
    """本日の成功履歴に記録された保存先とファイル名を、新しい順で返す。

    読み取りにも追記と同じロックを使うため、別プロセスが書いている途中の行を読まない。
    実ファイルの存在確認は呼び出し側で行い、古い成功ファイルへ遡れるよう全候補を返す。
    `trigger` 引数は互換のために残している（実行方式列は無くなった）。
    """
    _ = trigger  # 旧コードでは履歴の「実行方式」列を見ていたが、列を廃止したので未使用
    history_path = Path(path)
    target = (date or today()).strftime("%Y-%m-%d")
    key_text = str(report_key)
    if not history_path.is_file():
        logger.debug("履歴ファイル無し: path=%s, 件数=0", history_path)
        return []
    logger.debug(
        "本日成功履歴の検索開始: path=%s, 管理番号=%s, 日付=%s",
        history_path,
        key_text,
        target,
    )
    matches: list[Path] = []
    for row in _read_rows(history_path):
        if (
            row.get("実行日時", "").startswith(target)
            and row.get("管理番号", "") == key_text
            and row.get("成否", "") == SUCCESS
            and row.get("保存結果", "") == SUCCESS
            and row.get("ファイル名", "")
        ):
            matches.append(Path(row.get("保存先", "")) / row["ファイル名"])
    logger.debug("本日成功履歴の検索完了: path=%s, 該当件数=%d", history_path, len(matches))
    return list(reversed(matches))


@measure
def schedule_succeeded_today(
    path: str | Path,
    schedule_key: str,
    date: datetime.date | None = None,
) -> bool:
    """指定スケジュールキーが今日すでに成功したかを履歴から返す。

    ``download_scheduled()`` が同じスケジュール行を同日に何度も実行しないように
    するための判定。**ファイルの有無ではなく履歴で判定する。** 保存先にファイルが
    あっても、それが定期取得で置られたのか手で置いたのかは履歴を見ないと分からない。
    ``実行日時`` が当日で始まり、``成否 == 成功``、``保存結果 == 成功``、
    かつ ``スケジュールキー == schedule_key`` の行があれば True。

    空文字の ``schedule_key`` では呼ばない前提。呼び出し側で空文字のときはこの関数を
    呼ばないため。空文字で呼ばれた場合は履歴上どの
    スケジュールキーとも一致しないため必ず False を返す（誤って空文字を渡しても
    誤判定しない防御的挙動）。

    Args:
        path: 履歴 CSV のパス。
        schedule_key: スケジュール行のキー。
        date: 調べる日付。省略すると今日。

    Returns:
        当日に ``schedule_key`` で成功した履歴があれば True。
    """
    history_path = Path(path)
    target = (date or today()).strftime("%Y-%m-%d")
    key_text = str(schedule_key)
    if not history_path.is_file():
        logger.debug("履歴ファイル無し: path=%s, schedule_key=%s → False", history_path, key_text)
        return False
    if not key_text:
        # スケジュール行に紐付かないキーを渡された場合は、誤って他行と一致
        # させないため常に False。呼び出し側で弾くのが本来の形
        logger.debug("schedule_key が空文字: path=%s → 防御的に False", history_path)
        return False
    logger.debug(
        "スケジュールキー重複チェック開始: path=%s, schedule_key=%s, 日付=%s",
        history_path,
        key_text,
        target,
    )
    for row in _read_rows(history_path):
        if (
            row.get("実行日時", "").startswith(target)
            and row.get("スケジュールキー", "") == key_text
            and row.get("成否", "") == SUCCESS
            and row.get("保存結果", "") == SUCCESS
        ):
            logger.debug(
                "スケジュールキー当日成功済みを検出: path=%s, schedule_key=%s "
                "→ 今日は既に成功済みのためスキップ",
                history_path,
                key_text,
            )
            return True
    logger.debug(
        "スケジュールキー当日成功の検出なし: path=%s, schedule_key=%s → False",
        history_path,
        key_text,
    )
    return False


@measure
def truncated_today(
    path: str | Path,
    report_key: str,
    date: datetime.date | None = None,
) -> bool:
    """その日すでに2000件超（SalesforceReportTruncatedError）で失敗したかを返す。

    定期実行のたびに同じレポートが失敗し続けるのを防ぐため、``download_scheduled()``
    が対象選定の前に呼ぶ。1日1回失敗すれば、その日の残りの定期実行では
    スキップする（翌日になれば改めて1回だけ試す）。

    2000件超で失敗したまま放置すると毎日同じ失敗ログが積み上がるので、
    1日1回だけ試す方針にしてある。**永久に試さなくすると、レポートの
    規模が縮小した・SOQL へ切り替えたなどで状況が直ったあとに気づかず
    放置される**ため、翌日には改めて1回だけ試す形にした。
    ``downloaded_today()`` と同じ「履歴を正とする」判定で、ファイルの有無
    には依存しない。

    Args:
        path: 履歴 CSV のパス。
        report_key: 管理番号。
        date: 調べる日付。省略すると今日。

    Returns:
        ``SalesforceReportTruncatedError`` で失敗した履歴がその日に1件でも
        あれば True。履歴が無い／失敗の記録が無い／別のエラーコードの失敗は
        全て False。
    """
    history_path = Path(path)
    target = (date or today()).strftime("%Y-%m-%d")
    key_text = str(report_key)
    if not history_path.is_file():
        logger.debug(
            "2000件超失敗履歴の検索: path=%s → 履歴無しのため False",
            history_path,
        )
        return False
    logger.debug(
        "2000件超失敗履歴の検索開始: path=%s, 管理番号=%s, 日付=%s",
        history_path,
        key_text,
        target,
    )
    for row in _read_rows(history_path):
        if (
            row.get("実行日時", "").startswith(target)
            and row.get("管理番号", "") == key_text
            and row.get("成否", "") == FAILURE
            and row.get("エラーコード", "") == TRUNCATED_ERROR_NAME
        ):
            logger.debug(
                "2000件超失敗履歴を検出: path=%s, 管理番号=%s "
                "→ 当日中のため、この定期実行ではスキップ",
                history_path,
                key_text,
            )
            return True
    logger.debug(
        "2000件超失敗履歴の検出なし: path=%s, 管理番号=%s → False",
        history_path,
        key_text,
    )
    return False


@measure
def read_history(path: str | Path) -> Table:
    """履歴 CSV を全行読んで Table で返す。フィルタはしない。

    **Salesforceレポートダウンローダー側からも import して使う共有 API。**
    利用プロジェクトが「今日この管理番号は成功したか」を知りたいだけなら、
    この全件読み込みではなく ``downloaded_today()``（bool を返す）の方が
    単純で意図も伝わる。この関数は履歴全体を横断的に見たい処理のためのもの
    （例: Salesforceレポートダウンローダーが書き込む前に既存の履歴を
    一覧したいケース）。

    **絞り込みは呼び出し側が行う。** 日付・トリガ・成否の組合せは使う側でしか
    決まらないため、ここでは全件をそのまま Table で返す（列は全て文字列の
    まま、型変換はしない。必要な列だけ利用側で変換する）。
    読み取りにも追記と同じロックを使うので、別プロセスが書いている途中の行を
    読まない。

    ファイルが無ければ空の Table（``COLUMNS`` の列だけを持つ）を返す。
    見出しが古い構成でも ``migrate_row()`` で新構成に揃え直して返す
    （致命的に壊れた見出しは ``CSV`` クラスが ``CSVError`` で止める）。

    Args:
        path: 履歴 CSV のパス。

    Returns:
        履歴の各行を持つ Table。列は ``COLUMNS`` の順番のまま。
    """
    history_path = Path(path)
    if not history_path.is_file():
        logger.debug("履歴ファイル無し: path=%s, 件数=0", history_path)
        return Table(list(COLUMNS), [])
    logger.debug("履歴全件読み込み開始: path=%s", history_path)
    rows = _read_rows(history_path)
    logger.debug("履歴全件読み込み完了: path=%s, 件数=%d", history_path, len(rows))
    return Table(list(COLUMNS), rows)


def _read_rows(path: Path) -> list[dict[str, str]]:
    """履歴CSVをロックの中で読み、``COLUMNS`` 順に揃え直した行リストを返す。

    ファイルが無い場合は空リスト。``CSV`` クラスが文字コード自動判定・見出し
    検証（空・重複）・列数不一致の検出を行い、致命的な破損は ``CSVError``
    系の例外で通知される。 ``migrate_row()`` で増えた列は捨て、減った列は
    空文字で埋めて ``COLUMNS`` 順へ並べ直す（通常の列ずれはこの層で吸収）。

    読み取り関数（``successful_files_today`` / ``schedule_succeeded_today`` /
    ``truncated_today`` / ``read_history``）と、管理番号で取得済みを引く
    ``latest_report_path`` / ``latest_report`` / ``today_report`` /
    ``has_today_report`` が共通して通る入口。
    """
    if not path.is_file():
        return []
    with HistoryFileLock(path):
        with CSV(path, read_only=True) as csv_file:
            table = csv_file.read()
        return [migrate_row(row) for row in table.to_rows()]


def migrate_row(row: dict[str, str]) -> dict[str, str]:
    """行データを現在の ``COLUMNS`` 構成に揃え直す。

    列が増減・並び替わっていても、既存の値は保持しつつ ``COLUMNS`` の順に
    並べ直す。**増えた列は空文字**、**``COLUMNS`` に無い列は捨てる**。
    読み取りロジックが ``COLUMNS`` の列名を仮定して ``row.get(...)`` できるように
    形を整える役割。

    公開関数。書き込み側（Salesforceレポートダウンローダー側の ``record()``
    など）も同じ実装を使うため、このファイルに置いて呼び出し側で import する。
    """
    return {column: row.get(column, "") for column in COLUMNS}


# ── 管理番号で取得済みレポートを引く読み取り関数 ────────────────────────
# どれも**履歴だけを見る**（管理表は Salesforceレポートダウンローダー側に
# あり、comken は管理表を知らない）。「成功」は、履歴の `成否` が成功で、
# `保存先` / `ファイル名` が空でない行。パスは `保存先` / `ファイル名` から
# 組み立てる。「最も新しい」は `実行日時` で判断する（同じ時刻なら履歴の
# 後ろの行）。


def _latest_success_path(
    history_path: Path,
    report_key: str,
    date: datetime.date | None = None,
) -> Path | None:
    """管理番号について、今日（または指定日）の成功行のうち最も新しいパスを返す。

    **「今日」指定が無い呼び出し（`latest_report_path()`）では、日付フィルタを
    使わず全ての履歴を見る**。今日だけの指定（`today_report()` /
    `has_today_report()`）では、`successful_files_today()` と同じ判定で当日
    分だけを走査する。

    該当する成功行が無ければ ``None`` を返す。
    """
    key_text = str(report_key)
    if not history_path.is_file():
        return None
    target_prefix = (date or today()).strftime("%Y-%m-%d") if date is not None else None
    latest_timestamp = ""
    latest_path: Path | None = None
    for row in _read_rows(history_path):
        if row.get("管理番号", "") != key_text:
            continue
        if row.get("成否", "") != SUCCESS or row.get("保存結果", "") != SUCCESS:
            continue
        file_name = row.get("ファイル名", "")
        if not file_name:
            continue
        timestamp = row.get("実行日時", "")
        if target_prefix is not None and not timestamp.startswith(target_prefix):
            continue
        # 同じ実行日時のときは履歴の後ろの行を採用する（==、>= だと
        # 最初の同値、> だと最後の同値）。`successful_files_today()` と
        # 同じく reversed で末尾側を最新と扱う単純さで揃えるため、
        # 「同じなら履歴の後ろ」を実現するために ``>=`` を使う
        if timestamp >= latest_timestamp:
            latest_timestamp = timestamp
            latest_path = Path(row.get("保存先", "")) / file_name
    return latest_path


@measure
def latest_report_path(key: str) -> Path:
    """管理番号に対する「最も新しい成功履歴」のパスを返す。

    **履歴だけを参照する**（管理表は Salesforceレポートダウンローダー側）。
    「成功」は履歴の ``成否 == 成功`` かつ ``保存結果 == 成功`` かつ
    ``保存先``/``ファイル名`` が空でない行。「最も新しい」は ``実行日時``
    の降順で、同値なら履歴の後ろの行（同じ時刻で複数行あるケースを吸収）。

    履歴が無い／該当行が無い／記録はあるがファイルが消えている場合は
    ``ReportNotDownloadedError`` を送出する。メッセージに管理番号と
    対処（定期取得が動いているか履歴を確認、ファイルが消えていれば
    そのパス）を書く。

    履歴の場所は ``paths.HISTORY_PATH`` を**呼び出した時点で**読む
    （テストで差し替えられるように）。

    Args:
        key: 管理番号。

    Returns:
        該当する最新の取得済みファイルのパス。

    Raises:
        ReportNotDownloadedError: 該当行が無い／記録はあるが実ファイルが無い場合。
    """
    from comken.services.salesforce_downloader.paths import HISTORY_PATH

    history_path = Path(HISTORY_PATH)
    path = _latest_success_path(history_path, key)
    if path is None:
        logger.debug("最新の取得ファイル: 管理番号=%s → 履歴に該当なし", key)
        raise ReportNotDownloadedError(key, None, history_path)
    if not path.is_file():
        logger.debug(
            "最新の取得ファイル: 管理番号=%s path=%s → ファイルが消えている",
            key,
            path,
        )
        raise ReportNotDownloadedError(key, path, history_path)
    logger.debug("最新の取得ファイル: 管理番号=%s path=%s", key, path)
    return path


@measure
def latest_report(key: str) -> Table:
    """管理番号に対する「最も新しい成功履歴」のファイルを ``Table`` で返す。

    内部で ``latest_report_path()`` を呼ぶ。``CSV(..., read_only=True)`` で
    読むので、ファイルが巨大でも全件メモリに展開する前に ``Table`` で受ける
    （呼び出し側で ``to_rows()`` / ``index()`` などを使える）。

    Args:
        key: 管理番号。

    Returns:
        該当ファイルから読み取った ``Table``。

    Raises:
        ReportNotDownloadedError: 該当行が無い／記録はあるが実ファイルが無い場合。
        ComkenFileNotFoundError: パスは履歴にあるがファイルが消えている場合。
    """
    path = latest_report_path(key)
    logger.debug("履歴が指す最新の取得ファイルを使います: 管理番号=%s path=%s", key, path)
    with CSV(path, read_only=True) as csv_file:
        return csv_file.read()


@measure
def today_report(key: str) -> Table:
    """管理番号について、**今日**成功した履歴のうち最も新しいファイルを ``Table`` で返す。

    当日分の成功記録が無い場合は ``ReportNotDownloadedError`` を送出する
    （定期取得が動いていないか、実行時刻より前に呼ばれた、等）。

    Args:
        key: 管理番号。

    Returns:
        当日分の最新ファイルを読み取った ``Table``。

    Raises:
        ReportNotDownloadedError: 当日分の成功記録が無い／ファイルが消えている場合。
    """
    from comken.services.salesforce_downloader.paths import HISTORY_PATH

    history_path = Path(HISTORY_PATH)
    path = _latest_success_path(history_path, key, date=today())
    if path is None:
        logger.debug("本日の取得ファイル: 管理番号=%s → 当日分なし", key)
        raise ReportNotDownloadedError(key, None, history_path)
    if not path.is_file():
        logger.debug(
            "本日の取得ファイル: 管理番号=%s path=%s → ファイルが消えている",
            key,
            path,
        )
        raise ReportNotDownloadedError(key, path, history_path)
    logger.debug("本日の取得ファイル: 管理番号=%s path=%s", key, path)
    with CSV(path, read_only=True) as csv_file:
        return csv_file.read()


@measure
def has_today_report(key: str) -> bool:
    """管理番号について、今日成功した履歴があり実ファイルも残っていれば True。

    「今日取れているか」を**履歴だけで**判定する（ファイルの有無は確認する
    ので、履歴に残っていても手作業で消されたものは False になる）。

    Args:
        key: 管理番号。

    Returns:
        当日分の成功記録があり、かつ実ファイルも残っている場合は True。
        記録が無い／失敗／ファイルが消えている場合は False（例外を投げない）。
    """
    try:
        today_report(key)
    except ReportNotDownloadedError as error:
        logger.debug(
            "本日の取得ファイルの有無: 管理番号=%s → False（%s）",
            key,
            error,
        )
        return False
    logger.debug("本日の取得ファイルの有無: 管理番号=%s → True", key)
    return True


# ── 書き込み ────────────────────────────────────────────────────────────
@measure
def append_history(
    path: str | Path,
    values: Mapping[str, object],
    *,
    executed_at: dt.datetime | None = None,
) -> None:
    """履歴を1行追記する。ファイルが無ければ見出し行から作る。

    ダウンローダー側（旧 `record()`）がやっていた「ロック → ヘッダ確認 → 追記」を
    そのまま comken 側へ持ってきた。`values` には ``COLUMNS`` の列名をキーに
    した ``Mapping``（``ReportEntry`` から組み立てるなど、書き込み側が決めた
    もの）を渡す。**無い列は空文字**で埋め、**``COLUMNS`` に無いキーは
    ``InvalidTableInputError`` 相当の例外**で止める。**書き込みに失敗したら
    ``HistoryWriteError`` を送出する**（履歴は必須データなので、記録失敗は
    処理全体の失敗として扱う）。

    既存見出しが古い構成のときは、全行を ``migrate_row()`` で今の ``COLUMNS``
    に揃え直したうえで、新しい1行を足して **1回の保存で** 書き込む
    （マイグレーションと追記を別々に2回書き直さない）。既存見出しが
    重複・空など致命的に壊れていると、 ``CSV`` クラスがそのまま例外を
    上げてファイルは何も書き換えない。

    Args:
        path: 履歴 CSV のパス。
        values: ``COLUMNS`` の列名をキーにした ``Mapping``。例::

            {
                "実行日時": now().strftime("%Y-%m-%d %H:%M:%S"),
                "管理番号": entry.key,
                "スケジュールキー": row.schedule_key,
                "概要": entry.summary,
                "レポートID": entry.report_id,
                "URL": entry.url,
                "プロジェクト": project,
                "成否": "成功" if row.succeeded else "失敗",
                "Salesforce取得結果": _stage(row.fetched_from_salesforce),
                "保存結果": _stage(row.saved_to_file),
                "保存先": _resolved_folder(entry),
                "ファイル名": row.file_name,
                "取得件数": "" if row.row_count is None else row.row_count,
                "処理秒数": f"{row.seconds:.2f}",
                "原因区分": row.cause,
                "エラーコード": row.error_code,
                "エラー内容": row.error.replace("\n", " "),
            }

        executed_at: 「実行日時」列に書く値。**その実行の開始時刻**を 1 実行で
            固定して渡すことで、23:59 に始まった実行が日付をまたいでも、判定・
            ファイル名・履歴のすべてが開始日で揃う。``None`` のときは従来どおり
            ``now()``（呼び出した瞬間の時刻）で書く（テストなど、時刻固定が
            不要な呼び出し側の後方互換）。

    Raises:
        InvalidTableInputError: ``values`` に ``COLUMNS`` に無いキーが含まれている
            場合（タイポ・想定外の列名の混入）。
        HistoryWriteError: 書き込みに失敗した場合。
    """
    from comken.exceptions import HistoryWriteError

    path = Path(path)
    unknown_keys = [key for key in values if key not in COLUMNS]
    if unknown_keys:
        raise InvalidTableInputError(
            f"履歴の列として定義されていないキーが values に含まれています: {unknown_keys}\n"
            f"COLUMNS: {list(COLUMNS)}"
        )
    logger.debug(
        "履歴追記開始: path=%s, 管理番号=%s",
        path,
        values.get("管理番号", ""),
    )
    timestamp = now() if executed_at is None else executed_at
    record_dict: dict[str, object] = {column: values.get(column, "") for column in COLUMNS}
    record_dict["実行日時"] = timestamp.strftime(_TIMESTAMP_FORMAT)
    try:
        with HistoryFileLock(path):
            _append(path, record_dict)
    except HistoryWriteError:
        raise
    except (OSError, InvalidTableInputError) as exc:
        # ``InvalidTableInputError`` は、既存の履歴が CP932 のとき、その文字コードで表せない文字
        # （絵文字など）を書こうとした場合。履歴は必須データなので、記録失敗として扱う
        # （文字コードは変えない。元のファイルは無傷で残る）
        raise HistoryWriteError(path, str(exc)) from exc
    logger.debug("履歴追記完了: path=%s", path)


def _append(path: Path, record_dict: dict[str, object]) -> None:
    """1行を追記する。見出し行はファイルを作るときだけ書く。

    既存見出しが古い構成のときは、全行を ``migrate_row()`` で今の ``COLUMNS``
    に揃え直したうえで、新しい1行を足して **1回の保存で** 書き込む
    （マイグレーションと追記を別々に2回書き直さない）。既存見出しが
    重複・空など致命的に壊れていると、 ``CSV`` クラスがそのまま例外を
    上げてファイルは何も書き換えない。

    書き込みは ``comken.toolbox.csv.CSV`` クラスに委譲する。文字コード自動判定
    （UTF-8 BOM / CP932）・見出しの検証（空・重複）・列数不一致の検出は
    ``CSV`` クラスが担当する。書き換え後は次の追記と同じく UTF-8 BOM 付きへ
    正規化される（同じ ``with`` からの追記と整合させるため）。

    パフォーマンス面の注意: 1 回あたりにファイル全体を原子的に書き直すため、
    行数が増えるほど 1 回の書き込みコストは増える。履歴の規模
    （1 日数十件程度）では許容できる。

    この関数は ``HistoryFileLock`` の中で呼び出される前提になっている
    （``append_history()`` の呼び出し経路が ``with HistoryFileLock(path):`` 内）。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists() or path.stat().st_size == 0
    # ``is_new=True`` のときだけ ``columns=`` を渡す。既存ファイルに ``columns=``
    # を渡すと「見出しなしのファイル」扱いとなり、最初の1行をデータとして読んで
    # しまうため、渡すのは新規ファイル限定。
    with CSV(path, columns=list(COLUMNS) if is_new else None) as csv_file:
        if is_new:
            # CSV.append は ``dict[str, Value]`` を要求するが、``record_dict``
            # は ``Mapping[str, object]``。全ての値が文字列として扱えるので
            # ``str`` へ局所キャストして渡す
            csv_file.append({k: str(v) for k, v in record_dict.items()})
            return
        # 既存ファイル: ``CSV.read()`` が見出し検証（重複・空）を行う。
        # 検証失敗時の ``CSVError`` はそのまま呼出側へ伝播する
        table = csv_file.read()
        if tuple(table.columns) == COLUMNS:
            # 既に最新構成 → 既存 Table に 1 行足すだけ
            table.append({k: str(v) for k, v in record_dict.items()})
            csv_file.replace(table)
            return
        # 見出しが古い構成 → ``migrate_row`` で今の ``COLUMNS`` に揃え、
        # そこに今回の 1 行を足して 1 回で書き直す
        migrated_rows = [migrate_row(row) for row in table.to_rows()]
        new_table = Table(list(COLUMNS), migrated_rows)
        new_table.append({k: str(v) for k, v in record_dict.items()})
        csv_file.replace(new_table)
