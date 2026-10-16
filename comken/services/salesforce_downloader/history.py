"""comken/services/salesforce_downloader/history.py — 履歴CSVの列と、読み取り・書き込み。

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

**読み取りはファイルが更新されるまで結果を再利用する。** 履歴は増える一方で、
ダウンローダーの 1 実行で数百回判定するために ``_read_rows()`` を経由する。
``_read_rows()`` は ``(絶対パス, st_mtime_ns, st_size)`` をキーに結果を
キャッシュし、有効なら ``HistoryFileLock`` なしで返す（書き込み側がロックの
中でファイルを原子的に置き換えるため、読み取り側でロックを取る必要は無い）。
キャッシュの TTL は持たない（サイズの自然増加で無効化される）。詳細は
``_read_rows()`` の docstring と ``docs/HISTORY.md`` の新章を参照。

**追記は既存ファイルに対して末尾に1行だけ足す。** 既存実装は「ロック → 全件
``CSV.read()`` → 追記 → ``CSV.replace()``（原子的に全件書換え）」だったが、
履歴の行数が増えると 1 回の追記コストが膨らむため、見出しが現在の ``COLUMNS``
と一致し文字コードが UTF-8 のときは **速い経路** で ``open(path, "ab")`` の
``write()`` 1回だけにする（CSV 全体は書き換えない）。古い構成の見出しや
CP932 のときは従来どおり全件書換えの **遅い経路** に落ちる（マイグレーションと
文字コード正規化を1回の保存で済ませる）。詳細は ``_append()`` の docstring。
"""

import datetime
import datetime as dt
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from comken.core.dates import now, today
from comken.core.table import Table
from comken.core.timer import measure
from comken.exceptions import InvalidTableInputError, ReportNotDownloadedError
from comken.services.salesforce_downloader.history_file_lock import HistoryFileLock
from comken.toolbox.csv import CSV
from comken.toolbox.csv.file import encode_rows_as_bytes

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
    # API / SOQL / ブラウザ / 自動切替2種のいずれかを履歴に書く。管理表の
    # 「2000件超」「SOQL」列で経路が決まる（src/service.py::_fetch()）。
    # 2000件超 × かつ SOQL × の Report API 経路で失敗したときは、自動で
    # ブラウザ経由に切り替え（``SalesforceReportTruncatedError`` → 2000件超用 /
    # 0件 × → 0件用の2種）。初期導入前の履歴（この列が無い）は
    # ``migrate_row()`` で空文字に補われて読める
    "取得経路",
)

SUCCESS = "成功"
FAILURE = "失敗"

# 「取得経路」列に書く定数値。``history.py`` は経路の判定（管理表の列）を持たない
# ので、**実際にどう走ったか**だけを文字列として記録する。書き込み側
# （Salesforceレポートダウンローダー側 ``src/service.py::_fetch()``）が管理表
# の「2000件超」「SOQL」列を見て決め、これらの定数をそのまま履歴に書く。
# 自動切替2種は「Report API で失敗 → ブラウザで取り直して成功」の意味を持つ
# （Salesforce側で 2000件超で打ち止められていた／0件だった可能性があるので、
# 管理表を直すか SOQL 化を検討する運用ログとしても残す）
ROUTE_API = "API"
ROUTE_SOQL = "SOQL"
ROUTE_BROWSER = "ブラウザ"
ROUTE_BROWSER_FALLBACK_TRUNCATED = "ブラウザ（自動切替：2000件超）"
ROUTE_BROWSER_FALLBACK_EMPTY = "ブラウザ（自動切替：0件）"

_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
_DATE_FORMAT = "%Y-%m-%d"


# ── 読み取りキャッシュ（直近の1ファイルぶんのみ）────────────────────────
# キーは ``(絶対パス, st_mtime_ns, ファイルサイズ)``。TTL は持たない
# （サイズの自然増加で無効化される）。テストから差し替えられるよう別関数
# ``_clear_read_cache()`` を用意する。複数ファイルのキャッシュは持たない
# （履歴は1つだけ）。
_READ_CACHE_KEY: tuple[str, int, int] | None = None
_READ_CACHE_ROWS: list[dict[str, str]] | None = None


def _clear_read_cache() -> None:
    """読み取りキャッシュを破棄する（テスト専用）。

    本番の書き込み経路では ``_append`` 後にサイズが自然に増えるため
    不要だが、念のため ``append_history()`` からも明示的に呼ぶ。
    テストでは autouse fixture から呼んでテスト間の状態を切る。
    """
    global _READ_CACHE_KEY, _READ_CACHE_ROWS
    _READ_CACHE_KEY = None
    _READ_CACHE_ROWS = None


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
    route: str = ""  # API / SOQL / ブラウザ / 自動切替2種。空文字は不明または書き込まれなかった


# ── 読み取り ────────────────────────────────────────────────────────────
@measure
def downloaded_today(
    path: str | Path,
    report_key: str,
    date: datetime.date | None = None,
) -> bool:
    """その日の取得が成功しているかを履歴から調べる。

    **ファイルの有無ではなく履歴で判定する。** 保存先に今日の日付のファイルがあっても、
    それが定期取得で置かれたのか、手で置いたのかは分からない。
    「定期取得が動いているか」を知りたいので、履歴を正とする。

    Args:
        path: 履歴 CSV のパス。
        report_key: 管理番号。
        date: 調べる日付。省略すると今日。

    Returns:
        その日に成功した記録があれば True。履歴が無ければ False。
    """
    path = Path(path)
    return bool(successful_files_today(path, report_key, date))


@measure
def successful_files_today(
    path: str | Path,
    report_key: str,
    date: datetime.date | None = None,
) -> list[Path]:
    """本日の成功履歴に記録された保存先とファイル名を、新しい順で返す。

    読み取りにも追記と同じロックを使うため、別プロセスが書いている途中の行を読まない。
    実ファイルの存在確認は呼び出し側で行い、古い成功ファイルへ遡れるよう全候補を返す。
    """
    history_path = Path(path)
    target = (date or today()).strftime(_DATE_FORMAT)
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
    target = (date or today()).strftime(_DATE_FORMAT)
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
    """履歴CSVを読み、``COLUMNS`` 順に揃え直した行リストを返す。

    **ファイルが更新されるまで結果を再利用する（キャッシュ）。** キーは
    ``(絶対パス, st_mtime_ns, ファイルサイズ)``。TTL は持たない
    （サイズの自然増加で無効化される）。キャッシュが有効なら
    ``HistoryFileLock`` を取らずにそのまま返す。書き込み側はロックの中で
    ファイル全体を原子的に置き換えるので、読み取り側でロックを取る必要は無い
    （キャッシュの中身は「ロック中に読まれた整合性の取れた状態」）。

    **返り値は読み取り専用。** 呼び出し側は dict / list を書き換えない前提。
    同一プロセス内で使い回されるため、変更すると後続の呼び出しや他の読み取り
    経路にも影響する。 ``read_history()`` は ``Table`` を返すが、Table
    構築時に ``dict(row)`` でコピーされるため、利用側が ``read_history()``
    の ``to_rows()`` を書き換えても影響しない。

    読み込みの前後で ``stat`` が変わっていたら、そのキーでキャッシュに保存
    せずそのまま返す（読んでいる間に書き込まれたかもしれない古い結果を
    残さないため）。

    ファイルが無い場合は空リスト。``CSV`` クラスが文字コード自動判定・見出し
    検証（空・重複）・列数不一致の検出を行い、致命的な破損は ``CSVError``
    系の例外で通知される。 ``migrate_row()`` で増えた列は捨て、減った列は
    空文字で埋めて ``COLUMNS`` 順へ並べ直す（通常の列ずれはこの層で吸収）。

    読み取り関数（``successful_files_today`` / ``schedule_succeeded_today`` /
    ``read_history`` / ``report_path`` / ``read_report``）が共通して通る入口。
    """
    global _READ_CACHE_KEY, _READ_CACHE_ROWS
    abs_path = path.resolve()
    if not path.is_file():
        return []
    try:
        before_stat = abs_path.stat()
    except FileNotFoundError:
        return []
    cache_key = (str(abs_path), before_stat.st_mtime_ns, before_stat.st_size)
    if cache_key == _READ_CACHE_KEY and _READ_CACHE_ROWS is not None:
        return _READ_CACHE_ROWS
    with HistoryFileLock(path):
        with CSV(path, read_only=True) as csv_file:
            table = csv_file.read()
        rows = [migrate_row(row) for row in table.to_rows()]
    try:
        after_stat = abs_path.stat()
    except FileNotFoundError:
        # 読んでいるうちにファイルが消えた場合は、結果を返すがキャッシュには残さない
        return rows
    if (
        after_stat.st_mtime_ns == before_stat.st_mtime_ns
        and after_stat.st_size == before_stat.st_size
    ):
        # 読み込み前後でファイルが変わっていない → このキーで安心してキャッシュできる
        _READ_CACHE_KEY = cache_key
        _READ_CACHE_ROWS = rows
    return rows


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
# どちらも**履歴だけを見る**（管理表は Salesforceレポートダウンローダー側に
# あり、comken は管理表を知らない）。「最も新しい」は ``実行日時`` の降順で、
# 同値なら履歴の後ろの行。同じ実行日時の複数行を「後ろを採用」で吸収する。
#
# 重要なのは **「最新の行だけを見る」** こと: 古い成功行は「直近は取れていない」
# の救済には使わない。最新の行が失敗していれば、その管理番号は「取れていない」
# として扱う（古い成功ファイルを読んで業務が古いデータで動く事故を防ぐ）。
# 成否の判定は履歴の ``成否 == 成功`` かつ ``保存結果 == 成功`` かつ
# ``ファイル名`` が空でないこと。パスは ``保存先`` / ``ファイル名`` から組み立てる。


def _latest_row(
    history_path: Path,
    report_key: str,
    schedule_key: str | None = None,
) -> dict[str, str] | None:
    """管理番号（と任意のスケジュールキー）に合う履歴のうち、最も新しい1行を返す。

    日付フィルタは**使わない**。``report_path()`` / ``read_report()`` は
    全履歴の中の最新行を見て「最新の取得が成功しているか」を判定するため、
    ここで日付を切ると古い成功ファイルを「取れている」と誤認する事故になる。

    ``schedule_key`` を指定すると、履歴の「スケジュールキー」列がその値と
    **完全一致**する行だけを対象にする（部分一致にはしない）。``None``
    （省略）のときはスケジュールキーでの絞り込みは行わない。``S09``
    のような途中までで ``S0900`` の行を拾わないのはこのため。

    成否は問わない（呼び出し側で判定する）。履歴ファイルが無い／該当行が
    無いときは ``None`` を返す。
    """
    key_text = str(report_key)
    schedule_key_text = None if schedule_key is None else str(schedule_key)
    if not history_path.is_file():
        return None
    latest_timestamp = ""
    latest_row: dict[str, str] | None = None
    for row in _read_rows(history_path):
        if row.get("管理番号", "") != key_text:
            continue
        if schedule_key_text is not None and row.get("スケジュールキー", "") != schedule_key_text:
            continue
        timestamp = row.get("実行日時", "")
        # 同じ実行日時のときは履歴の後ろの行を採用する（==、>= だと
        # 最初の同値、> だと最後の同値）。`successful_files_today()` と
        # 同じく reversed で末尾側を最新と扱う単純さで揃えるため、
        # 「同じなら履歴の後ろ」を実現するために ``>=`` を使う
        if timestamp >= latest_timestamp:
            latest_timestamp = timestamp
            latest_row = row
    return latest_row


def _resolve_history_path() -> Path:
    """``paths.HISTORY_PATH`` を**呼び出した時点で**読んで ``Path`` で返す。

    テストで ``monkeypatch.setattr`` で差し替えられるように、関数内で読む
    （import 時に確定しない）。
    """
    from comken.services.salesforce_downloader.paths import HISTORY_PATH

    return Path(HISTORY_PATH)


@measure
def report_path(
    key: str,
    *,
    schedule_key: str | None = None,
) -> Path | None:
    """管理番号に対する、**最新の取得**が指すパスを返す。

    **履歴だけを参照する**（管理表は Salesforceレポートダウンローダー側）。
    「最新の取得」は ``実行日時`` の降順で、同値なら履歴の後ろの行を採用した
    1行を指す。**「最新の取得が失敗なら、古い成功ファイルへ遡らない。**
    古い成功行を返すと、業務側が古いデータで動いて定期取得が止まったことに気づけ
    なくなるため）。この関数が ``Path`` を返すのは「**最新の行が成功**かつ
    実ファイルが存在する」ときだけ。

    成功の判定は履歴の ``成否 == 成功`` かつ ``保存結果 == 成功`` かつ
    ``ファイル名`` が空でないこと。パスは ``保存先`` / ``ファイル名`` から
    組み立てる。

    ``schedule_key`` を指定すると、スケジュールキー列がその値と**完全一致**
    する行だけを対象にする（部分一致にはしない）。省略（``None``）のときは
    スケジュールキーでは絞り込まない。同じ管理番号に複数のスケジュール行
    から取得しているレポートで、スケジュール行ごとに分けたパスを引きたい
    ときの指定。例: ``report_path("1001", schedule_key="S0900")``。

    **見つからないときは ``None`` を返す**（例外にしない）。ここでの
    「見つからない」は:
        - 履歴ファイル自体が無い
        - 条件に合う行が無い（成否を問わない）
        - 条件に合う行のうち最新のものが成功だが、指しているファイルが消えている
        - 条件に合う行のうち最新のものが失敗（成功行が古いだけ）

    のいずれか。 ``read_report()`` が ``ReportNotDownloadedError`` を
    投げるかどうかの判定を兼ねるため、ファイルが消えているとき／最新の取得
    が失敗しているときも ``None`` を返す（呼び出し側で ``is not None`` を
    ``read_report()`` の前に挟む必要はない）。

    **ファイルの中身は読まない。** ファイルの有無（``Path.is_file()``）
    までで判定が終わるため、大きなレポートで CSV を開かない分、
    「取れているか」だけ確認する用途で使っても無駄なコストが
    掛からない。

    履歴の場所は ``paths.HISTORY_PATH`` を**呼び出した時点で**読む
    （テストで差し替えられるように）。

    Args:
        key: 管理番号。
        schedule_key: 絞り込みに使うスケジュールキー（完全一致）。
            ``None``（省略）のときは絞り込まない。

    Returns:
        最新の取得が成功で実ファイルが存在するときだけそのパス。見つからない
        ときは ``None``（最新の取得が失敗している場合も含む）。
    """
    try:
        return _find_report(key, schedule_key)
    except ReportNotDownloadedError:
        return None


def _find_report(key: str, schedule_key: str | None = None) -> Path:
    """管理番号（と任意のスケジュールキー）に合う履歴の最新行から、ファイルパスを返す。

    判定のすべてをここに集約する:
        - 履歴の ``管理番号`` が ``key`` と一致し、 ``schedule_key`` が ``None`` で
          ないときは ``スケジュールキー`` 列も完全一致する行のうち、最新の 1 行を見る
        - その最新行が「``成否 == 成功`` かつ ``保存結果 == 成功`` かつ
          ``ファイル名`` が空でない」かつ、組み立てた ``Path`` が実在すればそれを返す
        - 上記のいずれかが満たされないときは ``ReportNotDownloadedError`` を投げる

    「見つからない」の 3 通り（該当行が無い／最新が失敗／ファイルが消えている）
    を区別して ``ReportNotDownloadedError`` のメッセージに反映する。
    「実行日時」が空の失敗行でも「最新の取得が失敗」の文面が出るよう、
    ``failed_at`` には ``"（日時不明）"`` を補って渡す
    （``ReportNotDownloadedError`` は ``failed_at`` が渡されたかで「最新が失敗」を判定する）。

    ``logger.debug`` もここに 1 回ずつだけ書く（``report_path()`` と
    ``read_report()`` の両方で同じログが重複しないように）。

    Raises:
        ReportNotDownloadedError: 該当行が無い／最新の取得が失敗／指している
            ファイルが消えている場合。
    """
    history_path = _resolve_history_path()
    latest = _latest_row(history_path, key, schedule_key=schedule_key)
    if latest is None:
        logger.debug(
            "取得ファイル: 管理番号=%s, schedule_key=%s → 履歴に該当なし",
            key,
            schedule_key,
        )
        raise ReportNotDownloadedError(key, None, history_path, schedule_key=schedule_key)
    file_name = latest.get("ファイル名", "")
    if latest.get("成否", "") != SUCCESS or latest.get("保存結果", "") != SUCCESS or not file_name:
        # 最新の取得が失敗 → 古い成功行へは遡らない。メッセージに失敗行の情報を載せる
        failure_text = " / ".join(
            part
            for part in (
                latest.get("原因区分", ""),
                latest.get("エラーコード", ""),
                latest.get("エラー内容", ""),
            )
            if part
        )
        raw_failed_at = latest.get("実行日時", "")
        # 「実行日時」が空でも「最新の取得が失敗」の文面にするため、表示用に補完
        display_failed_at = raw_failed_at or "（日時不明）"
        logger.debug(
            "取得ファイル: 管理番号=%s, schedule_key=%s → 最新行が失敗"
            "（実行日時=%s）のため返さない",
            key,
            schedule_key,
            raw_failed_at,
        )
        raise ReportNotDownloadedError(
            key,
            None,
            history_path,
            schedule_key=schedule_key,
            failed_at=display_failed_at,
            failure=failure_text or None,
        )
    path = Path(latest.get("保存先", "")) / file_name
    if not path.is_file():
        logger.debug(
            "取得ファイル: 管理番号=%s, schedule_key=%s path=%s → ファイルが消えている",
            key,
            schedule_key,
            path,
        )
        raise ReportNotDownloadedError(key, path, history_path, schedule_key=schedule_key)
    logger.debug(
        "取得ファイル: 管理番号=%s, schedule_key=%s path=%s",
        key,
        schedule_key,
        path,
    )
    return path


@measure
def read_report(
    key: str,
    *,
    schedule_key: str | None = None,
) -> Table:
    """管理番号に対する、**最新の取得**のファイルを ``Table`` で返す。

    内部で ``_find_report()`` を呼んで最新の行を引き、それが成功でファイルが
    残っていれば ``CSV(path, read_only=True)`` で読むので、ファイルが巨大でも
    全件メモリに展開する前に ``Table`` で受ける（呼び出し側で ``to_rows()`` /
    ``index()`` などを使える）。

    ``schedule_key=`` を指定するとそのスケジュールキーに完全一致する行だけを
    対象とする。 ``report_path()`` と同じ判定を使う。

    見つからないときは ``ReportNotDownloadedError`` を送出する。メッセージには
    管理番号・``schedule_key``（指定していれば）・対処（定期取得が動いているか
    履歴を確認）・最新の取得が失敗しているときの ``実行日時``・``原因区分``・
    ``エラー内容``・ファイルが消えているときのそのパス、が入る
    （``ReportNotDownloadedError`` 側の組み立てに従う）。

    Args:
        key: 管理番号。
        schedule_key: 絞り込みに使うスケジュールキー（完全一致）。
            ``None``（省略）のときは絞り込まない。

    Returns:
        最新の取得が成功のとき、そのファイルから読み取った ``Table``。

    Raises:
        ReportNotDownloadedError: 該当行が無い／最新の取得が失敗／指している
            ファイルが消えている場合。最新の取得が失敗のときはメッセージに
            その ``実行日時`` と ``原因区分`` / ``エラー内容`` が入る。
    """
    path = _find_report(key, schedule_key)
    logger.debug(
        "取得ファイル: 管理番号=%s, schedule_key=%s path=%s を読み取り",
        key,
        schedule_key,
        path,
    )
    with CSV(path, read_only=True) as csv_file:
        return csv_file.read()


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
                "実行日時": now().strftime(_TIMESTAMP_FORMAT),
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
    # 書き込み後は明示的に読み取りキャッシュを捨てる。サイズは増えているので
    # stat の自然変化でも無効化されるが、念のため（テスト間のリーク防止も兼ねる）
    if _READ_CACHE_KEY is not None and Path(_READ_CACHE_KEY[0]).resolve() == path.resolve():
        _clear_read_cache()
    logger.debug("履歴追記完了: path=%s", path)


def _append(path: Path, record_dict: dict[str, object]) -> None:
    """1行を追記する。見出し行はファイルを作るときだけ書く。

    **速い経路（通常）**: 既存ファイルの見出しが現在の ``COLUMNS`` と一致し、
    文字コードが UTF-8 (BOM 付き／無し) のときは ``HistoryFileLock`` の中で
    ``open(path, "ab")`` の ``write()`` 1回で **末尾に1行だけ** 追記する。
    CSV 全体を書き直さない。 ``_append`` 以前の設計（CSV 追記＋
    Windows ファイルロックで直列化）に沿った動き。

    **遅い経路（フォールバック）**: 次のどれかに該当するときは従来どおり
    ``CSV`` クラスで全件読み、 ``migrate_row()`` で ``COLUMNS`` 順に揃え直した
    うえで ``replace()`` で **1回の保存で** 書き直す（マイグレーションと追記
    を別々に2回書き直さない）:

    - ファイルが無い／サイズが 0（新規ファイル扱い）
    - 見出しが ``COLUMNS`` と一致しない（古い構成。マイグレーションが必要）
    - 文字コードが UTF-8 でない（CP932 など。UTF-8 BOM 付きへの正規化が必要）
    - 見出しが壊れている（空・重複）→ そのまま ``CSVError`` で停止

    速い経路と遅い経路で、**書かれる行のバイト列は同じ** （Excel ダイヤの
    ``csv.DictWriter`` 出力と UTF-8 (BOM 付き／無し) エンコード）。

    **改行補正**: 速い経路で既存ファイルの末尾が改行で終わっていない（前回の
    書き込みが途中で切れた）場合は、先に改行（``\\n``）を足してから新しい行を
    書く。 CSV クラスが書く末尾の改行は ``\\r\\n`` だが、``\\n`` が末尾に
    あれば ``csv.reader`` が正しく ``\\r\\n`` 終端の1行を読めるので問題ない。

    この関数は ``HistoryFileLock`` の中で呼び出される前提になっている
    （``append_history()`` の呼び出し経路が ``with HistoryFileLock(path):`` 内）。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists() or path.stat().st_size == 0
    if is_new:
        # 新規ファイル: 見出し + 1 データ行を UTF-8 BOM 付きで書き出す。
        # 遅い経路と同じバイト列にするため ``csv.DictWriter`` の出力を
        # ``utf-8-sig`` でエンコードする
        _write_initial_history(path, record_dict)
        return
    # 既存ファイル: 速い経路を試す。判定に失敗したら遅い経路にフォールバック
    inspection = _inspect_existing_header(path)
    if inspection is not None:
        header_bytes, encoding = inspection
        expected_header_bytes = ",".join(COLUMNS).encode("utf-8")
        if header_bytes == expected_header_bytes and encoding in ("utf-8", "utf-8-sig"):
            _append_one_line(path, record_dict)
            return
    # 遅い経路: 既存実装どおり全件書換え（マイグレーションまたは文字コード正規化）
    with CSV(path, columns=None) as csv_file:
        # ``CSV.read()`` が見出し検証（重複・空）を行う。
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


def _write_initial_history(path: Path, record_dict: dict[str, object]) -> None:
    """新規ファイルに見出し + 1 データ行を UTF-8 BOM 付きで書く（内部用）。

    既存実装（``CSV(columns=...)`` で構築して ``append``）とバイト列が同じに
    なるよう ``comken.toolbox.csv.encode_rows_as_bytes`` の出力をそのまま
    ``utf-8-sig`` で書く。
    """
    column_row = {column: column for column in COLUMNS}
    data_row = {column: str(record_dict.get(column, "")) for column in COLUMNS}
    payload = encode_rows_as_bytes([column_row, data_row], write_bom=True, write_header=False)
    with path.open("wb") as binary:
        binary.write(payload)


def _inspect_existing_header(path: Path) -> tuple[bytes, str] | None:
    """既存ファイルの先頭 1 行を読み、文字コードと「先頭行のバイト列」を返す（内部用）。

    戻り値の 1 要素目は「改行を除いた最初の 1 行」を ``bytes`` で返す
    （``COLUMNS`` 順であるかの判定に使う）。2 要素目は ``utf-8-sig``
    （BOM 付き）または ``utf-8`` （BOM なし）。判定できなかったときは
    ``None`` を返し、呼び出し側で遅い経路にフォールバックする。
    """
    try:
        with path.open("rb") as binary:
            raw = binary.read(64 * 1024)
    except OSError:
        return None
    if not raw:
        return None
    if raw.startswith(b"\xef\xbb\xbf"):
        encoding = "utf-8-sig"
        raw = raw[3:]
    else:
        encoding = "utf-8"
    newline_pos = raw.find(b"\n")
    header_bytes = raw if newline_pos == -1 else raw[:newline_pos]
    # ``\r\n`` 改行（Excel ダイヤ）では \r が末尾に残る
    if header_bytes.endswith(b"\r"):
        header_bytes = header_bytes[:-1]
    return header_bytes, encoding


def _append_one_line(path: Path, record_dict: dict[str, object]) -> None:
    """既存ファイルに1行だけ追記する（内部用・速い経路）。

    ``CSV._write`` が ``csv.DictWriter`` で書く出力（``\\r\\n`` 区切り・
    Excel ダイヤの引用符規則）をバイト列化し、ファイル末尾が改行で終わって
    いなければ先に ``\\n`` を足してから ``open(path, "r+b")`` の ``write()``
    1回で書く。 ``comken.toolbox.csv.encode_rows_as_bytes`` が
    ``CSV._write`` とバイト互換であることを保証している。
    """
    new_row = {column: str(record_dict.get(column, "")) for column in COLUMNS}
    payload = encode_rows_as_bytes([new_row], write_bom=False, write_header=False)
    with path.open("r+b") as binary:
        binary.seek(0, os.SEEK_END)
        size = binary.tell()
        if size > 0:
            # 末尾の 1 バイトを読んで改行で終わっているか確認する。
            # 前回の書き込みが途中で切れたケース（電源断・プロセス強制終了）に
            # 対応する。 ``csv.reader`` は ``\n`` 終端の ``\r\n`` 行を正しく
            # 読めるので、補正は ``\n`` 1 文字で十分
            binary.seek(-1, os.SEEK_END)
            last_byte = binary.read(1)
            if last_byte != b"\n":
                binary.write(b"\n")
        binary.write(payload)
