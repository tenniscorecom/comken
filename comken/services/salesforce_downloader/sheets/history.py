"""comken/services/salesforce_downloader/sheets/history.py — 履歴CSVの列と、その読み取り。

**`sheets/` には、ワークブック・CSVの「1枚（1ファイル）」ごとに、そこにある列と
意味を宣言するモジュールを集めている**（`master.py` = レポート管理表シート、
`schedule.py` = スケジュールシート）。

**書き込みは 2026-09 に comken の外（Salesforceレポートダウンローダー）へ
切り出した。** ここに残っているのは「履歴CSVの列・1行の形（`COLUMNS` /
`HistoryRow`）」と「その形式で書かれた履歴を読む関数」だけ。書き込み側
（`record()` 相当）は外部プロジェクト側にあり、ここで定義する `COLUMNS` /
`HistoryRow` / `HistoryFileLock`（`history_file_lock.py`）を同じ契約として
import して使う。読み書きどちらの側も**同じ形式定義を参照する**ことで、
列やロックの取り方が2箇所で食い違う事故を防ぐ（詳しくは `__init__.py` の
履歴メモを参照）。

**管理表とは別のファイルにする。** 書く主体が違う（管理表は人、履歴はプログラム）ので
分けないと、人が開いている間にプログラムが保存できず履歴が飛ぶ。**CSV に追記する。**
複数のプロジェクトが同時に走るので、Excel を開いて保存し直す方式だと壊れる。

読み取りは comken 自前の ``CSV`` クラス（``comken.toolbox.csv.CSV``）に委譲する。
文字コード自動判定・見出しの検証（空・重複）は ``CSV`` が行うので、ここでは
「ロックを掛けて ``CSV`` で読み、行を ``migrate_row()`` で揃える」だけ繰り返す。
"""

import datetime
import logging
from dataclasses import dataclass
from pathlib import Path

from comken.core.clock import today
from comken.core.table.model import Table
from comken.core.timer import measure
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


@dataclass(frozen=True)
class HistoryRow:
    """履歴1行の「呼び出し側が組み立てる部分」。履歴の列と1対1。

    `entry` の5列（管理番号・概要・レポートID・URL・保存先）は書き込み側
    （Salesforceレポートダウンローダー）で取り出す。`fetched_from_salesforce` /
    `saved_to_file` は `True` / `False` / `None` の3状態で、未到達は `None`。
    `schedule_key` はスケジュール行に紐付く取得で値が入り、スケジュール行が
    無いレポートの取得（後方互換）は空文字。
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
    あっても、それが定期取得で置かれたのか手で置いたのかは履歴を見ないと分からない。
    ``実行日時`` が当日で始まり、``成否 == 成功``、``保存結果 == 成功``、
    かつ ``スケジュールキー == schedule_key`` の行があれば True。

    空文字の ``schedule_key`` では呼ばない前提。呼び出し側（Salesforceレポート
    ダウンローダーの ``_matched_schedule_key()``）で空文字のときはこの関数を
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
    （致命的に壊れた見出しは ``CSV`` クラスが ``CSVInvalidHeaderError`` で止める）。

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

    4 つの読み取り関数（``successful_files_today`` / ``schedule_succeeded_today``
    / ``truncated_today`` / ``read_history``）が共通して通る入口。
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

    公開関数。Salesforceレポートダウンローダー側の書き込み側マイグレーション
    （``history_writer._migrate_if_needed()``）からも同じ実装を使うため、
    comken 側に置いて呼び出し側で import する。
    """
    return {column: row.get(column, "") for column in COLUMNS}
