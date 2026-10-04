"""ダウンロード履歴の読み取り・書き込み関数を検証する。

2026-09 に「取る側」を comken の外（Salesforceレポートダウンローダー）へ移し、
comken 側は履歴の形式と「管理番号で取得済みレポートを引く」読み取り関数、
およびダウンローダー側から呼ばれる `append_history()` を共有している。
読み取り関数（`successful_files_today` / `schedule_succeeded_today` /
`truncated_today` / `read_history` / `report_path` / `read_report`）と
書き込み（`append_history`）の両方を検証する。
"""

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from comken.core.dates import now
from comken.exceptions import (
    CSVError,
    HistoryWriteError,
    InvalidTableInputError,
    ReportNotDownloadedError,
)
from comken.services.salesforce_downloader.history import (
    COLUMNS,
    FAILURE,
    ROUTE_API,
    ROUTE_BROWSER,
    ROUTE_BROWSER_FALLBACK_EMPTY,
    ROUTE_BROWSER_FALLBACK_TRUNCATED,
    ROUTE_SOQL,
    SUCCESS,
    HistoryRow,
    append_history,
    read_history,
    read_report,
    report_path,
    schedule_succeeded_today,
    successful_files_today,
    truncated_today,
)


@dataclass(frozen=True)
class _Entry:
    """テスト用の管理表1行のスタブ。

    ReportEntry 自体は comken の外（Salesforceレポートダウンローダー）へ移ったため、
    テストでは ``_Entry`` で代用し、``_write_row`` はキー・概要・レポートID・URL
    だけを ``_Entry`` から取る。
    """

    key: str = "1001"
    summary: str = "顧客一覧"
    url: str = "https://example.com/Report/00O5g00000ABCDE/view"

    @property
    def report_id(self) -> str:
        return "00O5g00000ABCDE"


# マイグレーションテスト用の固定 URL。``test_service.py`` と同じ値を使う（管理表の URL
# からレポート ID を取り出すテストは ``report_id`` 列が実 URL を要求するため）
URL_A = "https://example--sandbox.sandbox.my.salesforce.com/lightning/r/Report/00O5g00000ABCDE/view"


def _write_row(
    path: Path,
    *,
    entry: _Entry,
    project: str,
    row: HistoryRow,
    timestamp: str | None = None,
    target_folder: Path | None = None,
) -> None:
    """テスト用: 旧 `record()` 相当の1行をCSVへ直接書く（書き込み側は別リポジトリへ移動）。"""

    def _stage(value: bool | None) -> str:
        if value is None:
            return ""
        return SUCCESS if value else FAILURE

    values = [
        timestamp or now().strftime("%Y-%m-%d %H:%M:%S"),
        entry.key,
        row.schedule_key,
        entry.summary,
        entry.report_id,
        entry.url,
        project,
        SUCCESS if row.succeeded else FAILURE,
        _stage(row.fetched_from_salesforce),
        _stage(row.saved_to_file),
        str(target_folder) if target_folder is not None else entry.summary,
        row.file_name,
        "" if row.row_count is None else row.row_count,
        f"{row.seconds:.2f}",
        row.cause,
        row.error_code,
        row.error.replace("\n", " "),
        row.route,
    ]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(COLUMNS)
        writer.writerow(values)


def test_successful_file_requires_both_overall_and_save_success(tmp_path) -> None:
    """成否だけが成功でも、保存成功が無い履歴を取得済みにしない。"""
    history_path = tmp_path / "履歴.csv"
    entry = _entry()
    _write_row(
        history_path,
        entry=entry,
        project="異常な履歴",
        row=HistoryRow(True, True, False, file_name="not-saved.csv"),
    )

    assert successful_files_today(history_path, entry.key) == []


def test_read_history_returns_every_row_in_order(tmp_path) -> None:
    """絞り込みはせず、書かれた順のまま全行を Table で返す。"""
    history_path = tmp_path / "履歴.csv"
    entry = _entry()
    _write_row(
        history_path,
        entry=entry,
        project="P1",
        row=HistoryRow(True, True, True, file_name="a.csv"),
    )
    _write_row(
        history_path,
        entry=entry,
        project="P2",
        row=HistoryRow(True, True, True, file_name="b.csv"),
    )

    rows = read_history(history_path).to_rows()
    assert [row["プロジェクト"] for row in rows] == ["P1", "P2"]
    assert rows[0]["ファイル名"] == "a.csv"
    assert rows[1]["ファイル名"] == "b.csv"


def test_read_history_returns_empty_table_when_history_missing(tmp_path) -> None:
    """履歴が無いときは例外を出さず、列だけ持つ空の Table を返す。"""
    result = read_history(tmp_path / "無い.csv")
    assert len(result) == 0
    assert result.columns == list(COLUMNS)


def test_read_history_rejects_header_mismatch(tmp_path) -> None:
    """見出しが壊れている（空の見出しがある／列名が重複している）場合は
    ``CSVError`` で止める。

    列数が違う／列名が一部欠落している／順序が違う程度の変更は
    ``migrate_row()`` で吸収するため、ここでは**致命的に壊れたケース**
    （=どの列値をどの列に読んだか曖昧になるケース）だけを弾く。
    検出は comken 自前の ``CSV`` クラスが行い、共通の ``CSVError`` 系の
    例外で通知される（履歴専用の例外は存在しない）。
    """
    history_path = tmp_path / "履歴.csv"
    # 2列目に空文字の見出し = ``DictReader`` が列値の対応を取れない壊れ方
    history_path.write_text("管理番号,,成否\n1000,x,成功\n", encoding="utf-8-sig")

    with pytest.raises(CSVError):
        read_history(history_path)


def test_read_history_rejects_duplicate_headers(tmp_path) -> None:
    """見出しに重複がある場合も ``CSVError`` で止める。

    ``DictReader`` の列名の対応が曖昧になるため、致命的に壊れたケースとして
    共通の ``CSV`` クラスの例外で通知される。
    """
    history_path = tmp_path / "履歴.csv"
    # 2列目と4列目の見出しが重複している壊れた見出し
    history_path.write_text(
        "管理番号,管理番号,成否,管理番号\n1000,x,成功,y\n",
        encoding="utf-8-sig",
    )

    with pytest.raises(CSVError):
        read_history(history_path)


def test_successful_files_today_rejects_bad_header(tmp_path) -> None:
    """``successful_files_today`` も見出しの致命的な破損を ``CSVError`` で止める。

    4 つの読み取り関数は共通ヘルパー ``_read_rows`` を通るため、同じ例外で
    検出される（履歴専用の例外クラスを新設しない）。
    """
    history_path = tmp_path / "履歴.csv"
    history_path.write_text(",,,\n1000,x,成功,z\n", encoding="utf-8-sig")

    with pytest.raises(CSVError):
        successful_files_today(history_path, "1001")


def test_schedule_succeeded_today_rejects_bad_header(tmp_path) -> None:
    """``schedule_succeeded_today`` も見出しの致命的な破損を ``CSVError`` で止める。"""
    history_path = tmp_path / "履歴.csv"
    history_path.write_text(
        "管理番号,管理番号,成否,管理番号\n1000,x,成功,y\n",
        encoding="utf-8-sig",
    )

    with pytest.raises(CSVError):
        schedule_succeeded_today(history_path, "S001")


def test_truncated_today_rejects_bad_header(tmp_path) -> None:
    """``truncated_today`` も見出しの致命的な破損を ``CSVError`` で止める。"""
    history_path = tmp_path / "履歴.csv"
    history_path.write_text(",,,\n1000,x,成功,z\n", encoding="utf-8-sig")

    with pytest.raises(CSVError):
        truncated_today(history_path, "1001")


def test_schedule_succeeded_today_returns_true_after_same_key_success(tmp_path) -> None:
    """同じスケジュールキーで当日成功した履歴があれば True を返す。"""
    history_path = tmp_path / "履歴.csv"
    entry = _entry()
    _write_row(
        history_path,
        entry=entry,
        project="P",
        row=HistoryRow(
            True,
            True,
            True,
            file_name="a.csv",
            schedule_key="S001",
        ),
    )
    assert schedule_succeeded_today(history_path, "S001") is True


def test_schedule_succeeded_today_returns_false_when_no_record(tmp_path) -> None:
    """履歴が無いとき False を返す。"""
    assert schedule_succeeded_today(tmp_path / "無い.csv", "S001") is False


def test_schedule_succeeded_today_ignores_other_keys(tmp_path) -> None:
    """別スケジュールキーの成功履歴は True にしない。"""
    history_path = tmp_path / "履歴.csv"
    entry = _entry()
    _write_row(
        history_path,
        entry=entry,
        project="P",
        row=HistoryRow(
            True,
            True,
            True,
            file_name="a.csv",
            schedule_key="S002",
        ),
    )
    assert schedule_succeeded_today(history_path, "S001") is False


def test_schedule_succeeded_today_ignores_other_dates(tmp_path) -> None:
    """昨日の成功履歴は True にしない。"""
    history_path = tmp_path / "履歴.csv"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        (
            "実行日時,管理番号,スケジュールキー,概要,レポートID,URL,プロジェクト,"
            "成否,Salesforce取得結果,保存結果,保存先,ファイル名,取得件数,処理秒数,"
            "原因区分,エラーコード,エラー内容\n"
            "2024-01-01 09:00:00,1001,S001,顧客一覧,,,,成功,成功,成功,,a.csv,1,0.10,,,"
        ),
        encoding="utf-8-sig",
    )
    assert schedule_succeeded_today(history_path, "S001") is False


def test_schedule_succeeded_today_requires_save_success(tmp_path) -> None:
    """成否=成功でも保存結果=失敗なら True にしない（保存できていないので再試行可）。"""
    history_path = tmp_path / "履歴.csv"
    entry = _entry()
    _write_row(
        history_path,
        entry=entry,
        project="P",
        row=HistoryRow(
            True,
            True,
            False,
            file_name="not-saved.csv",
            schedule_key="S001",
        ),
    )
    assert schedule_succeeded_today(history_path, "S001") is False


def test_schedule_succeeded_today_rejects_empty_key(tmp_path) -> None:
    """空文字のスケジュールキーは何を引いても False を返す。

    呼び出し側で空文字を弾くのが本来の形だが、誤って渡された場合の防御として
    False を返す（誤マッチで別行と一致させないため）。
    """
    history_path = tmp_path / "履歴.csv"
    entry = _entry()
    _write_row(
        history_path,
        entry=entry,
        project="P",
        row=HistoryRow(
            True,
            True,
            True,
            file_name="a.csv",
            schedule_key="S001",
        ),
    )
    assert schedule_succeeded_today(history_path, "") is False


def test_truncated_today_returns_true_when_today_failed_with_truncated_error(tmp_path) -> None:
    """今日 ``SalesforceReportTruncatedError`` で失敗した履歴があれば True。"""
    history_path = tmp_path / "履歴.csv"
    entry = _entry()
    _write_row(
        history_path,
        entry=entry,
        project="P",
        row=HistoryRow(
            succeeded=False,
            fetched_from_salesforce=True,
            saved_to_file=None,
            cause="Salesforce",
            error_code="SalesforceReportTruncatedError",
            error="2000 行で打ち止め",
        ),
    )
    assert truncated_today(history_path, entry.key) is True


def test_truncated_today_returns_false_when_history_missing(tmp_path) -> None:
    """履歴ファイルが無い場合は例外を出さず False。"""
    assert truncated_today(tmp_path / "無い.csv", "1001") is False


def test_truncated_today_returns_false_for_other_error_codes(tmp_path) -> None:
    """今日の失敗でも、エラーコードが ``SalesforceReportTruncatedError``
    以外（例: 通信エラー、``OSError``）なら False。2000件超以外の失敗は
    毎回リトライしてよい、という既存挙動を壊さない。"""
    history_path = tmp_path / "履歴.csv"
    entry = _entry()
    _write_row(
        history_path,
        entry=entry,
        project="P",
        row=HistoryRow(
            succeeded=False,
            fetched_from_salesforce=True,
            saved_to_file=False,
            cause="ファイル",
            error_code="OSError",
            error="共有サーバー断",
        ),
    )
    assert truncated_today(history_path, entry.key) is False


def test_truncated_today_ignores_other_report_keys(tmp_path) -> None:
    """別の管理番号の 2000件超 失敗履歴は True にしない。"""
    history_path = tmp_path / "履歴.csv"
    entry = _entry()
    _write_row(
        history_path,
        entry=entry,
        project="P",
        row=HistoryRow(
            succeeded=False,
            fetched_from_salesforce=True,
            saved_to_file=None,
            cause="Salesforce",
            error_code="SalesforceReportTruncatedError",
            error="2000 行で打ち止め",
        ),
    )
    assert truncated_today(history_path, "別の管理番号") is False


def test_truncated_today_ignores_other_dates(tmp_path) -> None:
    """昨日の ``SalesforceReportTruncatedError`` 失敗は True にしない
    （翌日に改めて1回だけ試すため、日付をまたいだらリセットする）。"""
    history_path = tmp_path / "履歴.csv"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        (
            "実行日時,管理番号,スケジュールキー,概要,レポートID,URL,プロジェクト,"
            "成否,Salesforce取得結果,保存結果,保存先,ファイル名,取得件数,処理秒数,"
            "原因区分,エラーコード,エラー内容\n"
            "2024-01-01 09:00:00,1001,,,,,,失敗,成功,,,,,1.00,Salesforce,"
            "SalesforceReportTruncatedError,2000 行で打ち止め"
        ),
        encoding="utf-8-sig",
    )
    assert truncated_today(history_path, "1001") is False


def test_truncated_today_ignores_successful_rows_with_same_code(tmp_path) -> None:
    """同じエラーコードの文字列が成否=成功の行に書かれていても False
    （あり得ない組合せだが、列値の照合順の防御として明示的に区別する）。"""
    history_path = tmp_path / "履歴.csv"
    entry = _entry()
    _write_row(
        history_path,
        entry=entry,
        project="P",
        row=HistoryRow(
            succeeded=True,
            fetched_from_salesforce=True,
            saved_to_file=True,
            file_name="a.csv",
            error_code="SalesforceReportTruncatedError",
        ),
    )
    assert truncated_today(history_path, entry.key) is False


# ── 「取得経路」列（2026-10 追加） ────────────────────────────
class TestRouteColumn:
    """``取得経路`` 列の読み書き・マイグレーションを検証する。``ROUTE_*`` 定数が
    定義されていること、``HistoryRow.route`` の既定が空文字で後方互換なこと、
    古い履歴（この列が無いもの）が ``migrate_row()`` で空文字に補われて読めること
    を確認する。"""

    def test_route_constants_are_defined(self) -> None:
        from comken.services.salesforce_downloader.history import (
            ROUTE_BROWSER_FALLBACK_TRUNCATED,
        )

        # 書き込み側（Salesforceレポートダウンローダー側 ``src.service``）が
        # この文字列をそのまま履歴に書くので、業務担当者に見える値になる
        assert ROUTE_API == "API"
        assert ROUTE_SOQL == "SOQL"
        assert ROUTE_BROWSER == "ブラウザ"
        assert ROUTE_BROWSER_FALLBACK_TRUNCATED == "ブラウザ（自動切替：2000件超）"
        assert ROUTE_BROWSER_FALLBACK_EMPTY == "ブラウザ（自動切替：0件）"

    def test_route_column_is_in_columns_tuple(self) -> None:
        """``COLUMNS`` の最後尾に「取得経路」がある（順序が既存列の契約）。"""
        assert COLUMNS[-1] == "取得経路"

    def test_history_row_route_default_is_empty_string(self) -> None:
        """``HistoryRow.route`` の既定値は空文字。古い呼び出し側が ``route=`` を
        指定しなくても例外にならない（後方互換）。"""
        row = HistoryRow(True, True, True, file_name="a.csv")
        assert row.route == ""

    def test_read_history_returns_route_value(self, tmp_path) -> None:
        """``_write_row()`` で ``route=`` を指定した値が履歴からそのまま読める。"""
        history_path = tmp_path / "履歴.csv"
        entry = _entry()
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(
                True, True, True, file_name="a.csv", route=ROUTE_BROWSER_FALLBACK_TRUNCATED
            ),
        )

        rows = read_history(history_path).to_rows()
        assert len(rows) == 1
        assert rows[0]["取得経路"] == ROUTE_BROWSER_FALLBACK_TRUNCATED

    def test_legacy_history_without_route_column_is_migrated_with_empty_string(
        self, tmp_path
    ) -> None:
        """「取得経路」列が無い古い履歴（17 列構成）でも ``migrate_row()`` が
        空文字に補って ``COLUMNS`` 順で読める。例外を出さず、業務担当者が
        「列が壊れた」と誤認しないこと。
        """
        history_path = tmp_path / "履歴.csv"
        # 17 列の古い構成（取得経路が無い）。``COLUMNS[:-1]`` で 17 列を再現
        legacy_header = list(COLUMNS[:-1])
        legacy_values = _today_row_values()[: len(legacy_header)]
        _write_csv_raw(history_path, header=legacy_header, rows=[legacy_values])

        rows = read_history(history_path).to_rows()
        assert len(rows) == 1
        # 増えた列は空文字で埋められる
        assert rows[0]["取得経路"] == ""
        # 既存列の値は保持
        assert rows[0]["管理番号"] == "1001"


def _entry() -> _Entry:
    """各テストで同じ管理表1行を使う。"""
    return _Entry()


def _write_row_cp932(path: Path, *, entry: _Entry, project: str, row: HistoryRow) -> None:
    """テスト用: ``CP932`` で1行書く（Excel で開いて保存し直した履歴を再現）。

    人が Excel で開いて上書き保存すると CP932 化するため、``read_text()`` 側が
    それを吸収できることを確認する。日本語列名が CP932 のバイト列にしか
    乗らないため、UTF-8 試行が失敗して CP932 経路を通る。
    """

    def _stage(value: bool | None) -> str:
        if value is None:
            return ""
        return SUCCESS if value else FAILURE

    values = [
        now().strftime("%Y-%m-%d %H:%M:%S"),
        entry.key,
        row.schedule_key,
        entry.summary,
        entry.report_id,
        entry.url,
        project,
        SUCCESS if row.succeeded else FAILURE,
        _stage(row.fetched_from_salesforce),
        _stage(row.saved_to_file),
        # 保存先の組み立て（group_settings 経由）は他の場所で扱うので、ここでは概要だけ書く
        entry.summary,
        row.file_name,
        "" if row.row_count is None else row.row_count,
        f"{row.seconds:.2f}",
        row.cause,
        row.error_code,
        row.error.replace("\n", " "),
        row.route,
    ]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="cp932", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(COLUMNS)
        writer.writerow(values)


# ── 文字コード自動判定（人が Excel で開いて保存し直した履歴の吸収） ──
class TestEncodingAutoDetection:
    """``read_text()`` が UTF-8 (BOM 付き) と CP932 の自動判定で両方読めること。"""

    def test_read_history_handles_cp932_encoded_file(self, tmp_path) -> None:
        """CP932 で保存された履歴も読み取れる（Excel 経由で再保存した履歴）。"""
        history_path = tmp_path / "履歴.csv"
        entry = _entry()
        _write_row_cp932(
            history_path,
            entry=entry,
            project="案件集計",
            row=HistoryRow(True, True, True, file_name="a.csv"),
        )
        # 列名・値ともに日本語が含まれるため UTF-8 経由は失敗し、CP932 で復号される
        rows = read_history(history_path).to_rows()
        assert len(rows) == 1
        assert rows[0]["管理番号"] == "1001"
        assert rows[0]["プロジェクト"] == "案件集計"
        assert rows[0]["ファイル名"] == "a.csv"

    def test_successful_files_today_handles_cp932_encoded_file(self, tmp_path) -> None:
        """CP932 の履歴から当日の成功ファイル名を取れる。"""
        history_path = tmp_path / "履歴.csv"
        entry = _entry()
        _write_row_cp932(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(True, True, True, file_name="a.csv"),
        )
        matches = successful_files_today(history_path, entry.key)
        # 保存先は ``_write_row_cp932`` 内で ``entry.summary`` を入れる（テスト簡略化のため）
        assert matches == [Path(entry.summary) / "a.csv"]

    def test_schedule_succeeded_today_handles_cp932_encoded_file(self, tmp_path) -> None:
        """CP932 の履歴から当日同キーの成功を判定できる。"""
        history_path = tmp_path / "履歴.csv"
        entry = _entry()
        _write_row_cp932(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(True, True, True, file_name="a.csv", schedule_key="S001"),
        )
        assert schedule_succeeded_today(history_path, "S001") is True

    def test_truncated_today_handles_cp932_encoded_file(self, tmp_path) -> None:
        """CP932 の履歴から ``SalesforceReportTruncatedError`` の当日失敗を拾える。"""
        history_path = tmp_path / "履歴.csv"
        entry = _entry()
        _write_row_cp932(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(
                succeeded=False,
                fetched_from_salesforce=True,
                saved_to_file=None,
                cause="Salesforce",
                error_code="SalesforceReportTruncatedError",
                error="2000 行で打ち止め",
            ),
        )
        assert truncated_today(history_path, entry.key) is True

    def test_read_history_rejects_undecodable_file(self, tmp_path) -> None:
        """UTF-8 / CP932 のどちらでも読めないバイト列は明示的にエラーにする。

        エンコーディングを握りつぶすと「読めたように見えて壊れた値」の事故に
        つながるため、``CSVError`` で停止する。
        """
        history_path = tmp_path / "履歴.csv"
        history_path.write_bytes(b"\x80\x81\x82\x83")  # UTF-8 / CP932 どちらでも読めないバイト列

        with pytest.raises(CSVError):
            read_history(history_path)


# ── 列構成マイグレーション（COLUMNS 追加・削除・並び替え） ─────────────────────
def _write_csv_raw(path: Path, header: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
    """テスト用: 任意の列構成で履歴CSVを書く（COLUMNS 以外も書ける）。

    ``_write_row()`` は ``COLUMNS`` 固定のヘルパーなので、COLUMNS と違う列構成を
    試したいテストでは直接このヘルパーで書く。出力は ``_append()`` と同じく
    UTF-8 BOM 付きにする（``read_text()`` の UTF-8 経路で読める）。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


def _today_row_values(
    *, schedule_key: str = "", error_code: str = "", result: str = SUCCESS
) -> list[str]:
    """COLUMNS 順の今日日付1行を組み立てる（テストで使う基本データ）。"""
    today_str = now().strftime("%Y-%m-%d %H:%M:%S")
    return [
        today_str,  # 実行日時
        "1001",  # 管理番号
        schedule_key,  # スケジュールキー
        "顧客一覧",  # 概要
        "00O5g00000ABCDE",  # レポートID
        URL_A,  # URL
        "定期実行",  # プロジェクト
        result,  # 成否
        SUCCESS,  # Salesforce取得結果
        SUCCESS,  # 保存結果
        "顧客一覧",  # 保存先（テスト簡略化のため概要で代用）
        "a.csv",  # ファイル名
        "1",  # 取得件数
        "0.10",  # 処理秒数
        "",  # 原因区分
        error_code,  # エラーコード
        "",  # エラー内容
        "",  # 取得経路
    ]


class TestHeaderMigration:
    """``COLUMNS`` の列追加・削除・並び替えがあっても、読み込み側が動くこと。

    管理表マイグレーション（``create_template()``）と同じ「増えた列は空文字、
    減った列は捨て、並び順は新しい定義順」のルールを履歴CSV側にも適用する。
    """

    def test_extra_column_at_end_is_absorbed(self, tmp_path) -> None:
        """COLUMNS に無い列が末尾にあるCSVでも、既存データは保持して読み込める。

        増えた列（COLUMNS に無い列）は ``migrate_row()`` が捨てて、新しい
        ``COLUMNS`` 順の Table を返す。値が捨てられた事自体はログや例外で
        騒がず、黙って吸収する。
        """
        history_path = tmp_path / "履歴.csv"
        # 末尾に「新しい列」を足した17列の見出し
        extra_header = [*COLUMNS, "新列"]
        _write_csv_raw(
            history_path,
            header=[*extra_header],
            rows=[[*_today_row_values(), "追加された値"]],
        )

        rows = read_history(history_path).to_rows()
        assert len(rows) == 1
        # 返り値の Table は ``COLUMNS`` の列だけを持つ（追加された列は捨てた）
        assert list(rows[0].keys()) == list(COLUMNS)
        # 既存列の値は保持される
        assert rows[0]["管理番号"] == "1001"
        assert rows[0]["ファイル名"] == "a.csv"

    def test_missing_last_column_is_filled_with_empty(self, tmp_path) -> None:
        """COLUMNS の末尾列が無い古いCSVでも、最後の列を空文字として読み込める。"""
        history_path = tmp_path / "履歴.csv"
        # 「エラー内容」を抜いた15列の見出し（古いバージョン想定）
        old_header = list(COLUMNS[:-1])
        _write_csv_raw(
            history_path,
            header=old_header,
            rows=[_today_row_values()[: len(old_header)]],
        )

        rows = read_history(history_path).to_rows()
        assert len(rows) == 1
        # 抜けた列は空文字で埋められる
        assert rows[0]["エラー内容"] == ""
        assert rows[0]["管理番号"] == "1001"

    def test_reordered_columns_are_normalized_to_current_order(self, tmp_path) -> None:
        """COLUMNS の順序が違う古いCSVでも、各値は現在の ``COLUMNS`` 順で読める。"""
        history_path = tmp_path / "履歴.csv"
        # 「管理番号」「実行日時」「プロジェクト」「成否」を先頭に並べ替えた
        # 古い構成。値の並びもそれに揃える
        reordered_header = [
            "管理番号",
            "実行日時",
            "プロジェクト",
            "成否",
            *[
                column
                for column in COLUMNS
                if column not in {"管理番号", "実行日時", "プロジェクト", "成否"}
            ],
        ]
        # 値はヘッダーと同じ並びで書く。5 列目以降は元の COLUMNS 順のうち
        # 先頭4列を除いた残り
        reordered_values = [
            "1001",  # 管理番号
            now().strftime("%Y-%m-%d %H:%M:%S"),  # 実行日時
            "定期実行",  # プロジェクト
            SUCCESS,  # 成否
            "",  # スケジュールキー
            "顧客一覧",  # 概要
            "00O5g00000ABCDE",  # レポートID
            URL_A,  # URL
            SUCCESS,  # Salesforce取得結果
            SUCCESS,  # 保存結果
            "顧客一覧",  # 保存先
            "a.csv",  # ファイル名
            "1",  # 取得件数
            "0.10",  # 処理秒数
            "",  # 原因区分
            "",  # エラーコード
            "",  # エラー内容
            "",  # 取得経路
        ]
        _write_csv_raw(history_path, header=reordered_header, rows=[reordered_values])

        rows = read_history(history_path).to_rows()
        assert len(rows) == 1
        # ``migrate_row()`` が ``COLUMNS`` 順へ並べ直すため、列名で値を取れる
        assert rows[0]["管理番号"] == "1001"
        assert rows[0]["実行日時"].startswith(now().strftime("%Y-%m-%d"))
        assert rows[0]["成否"] == SUCCESS
        assert rows[0]["ファイル名"] == "a.csv"

    def test_extra_column_does_not_break_successful_files_today(self, tmp_path) -> None:
        """列追加があっても ``successful_files_today()`` が当日成功を拾える。"""
        history_path = tmp_path / "履歴.csv"
        extra_header = [*COLUMNS, "新列"]
        _write_csv_raw(
            history_path,
            header=[*extra_header],
            rows=[[*_today_row_values(), "追加された値"]],
        )

        matches = successful_files_today(history_path, "1001")
        assert matches == [Path("顧客一覧") / "a.csv"]

    def test_missing_column_does_not_break_schedule_succeeded_today(self, tmp_path) -> None:
        """列欠落があっても ``schedule_succeeded_today()`` が例外を出さない。

        「スケジュールキー」列が無い古いCSVでも、読み込み側で ``migrate_row()``
        が吸収して ``COLUMNS`` 順の行へ揃え直すため、判定ロジックは通常通り動く。
        古い構成ではスケジュールキーが無いので ``schedule_key == ""`` となり、
        渡した ``S001`` とは一致しない（防御的に False を返す）。
        """
        history_path = tmp_path / "履歴.csv"
        # 「スケジュールキー」と「エラー内容」を両方抜いた古い構成
        old_header = [c for c in COLUMNS if c not in {"スケジュールキー", "エラー内容"}]
        old_values_full = _today_row_values(schedule_key="S001")
        # 抜けた列ぶんを除いた値で書く（古い見出し 15 列に合わせる）
        old_values = [
            value
            for header, value in zip(COLUMNS, old_values_full, strict=True)
            if header in set(old_header)
        ]
        _write_csv_raw(history_path, header=old_header, rows=[old_values])

        # 旧バージョンのヘッダーでも例外を出さず、防御的に False を返す
        assert schedule_succeeded_today(history_path, "S001") is False

    def test_reordered_columns_do_not_break_truncated_today(self, tmp_path) -> None:
        """列並び替えがあっても ``truncated_today()`` が truncated エラーを拾える。"""
        history_path = tmp_path / "履歴.csv"
        # 失敗行（``SalesforceReportTruncatedError``）を「管理番号/実行日時/成否/
        # エラーコード」が先頭に並ぶ古い順で書く
        reordered_header = [
            "管理番号",
            "実行日時",
            "成否",
            "エラーコード",
            *[
                column
                for column in COLUMNS
                if column not in {"管理番号", "実行日時", "成否", "エラーコード"}
            ],
        ]
        truncated_values = [
            "1001",
            now().strftime("%Y-%m-%d %H:%M:%S"),
            FAILURE,
            "SalesforceReportTruncatedError",
            "",  # スケジュールキー
            "顧客一覧",  # 概要
            "00O5g00000ABCDE",  # レポートID
            URL_A,  # URL
            "定期実行",  # プロジェクト
            SUCCESS,  # Salesforce取得結果
            "",  # 保存結果
            "",  # 保存先
            "",  # ファイル名
            "",  # 取得件数
            "1.00",  # 処理秒数
            "Salesforce",  # 原因区分
            "",  # エラー内容
            "",  # 取得経路
        ]
        _write_csv_raw(history_path, header=reordered_header, rows=[truncated_values])

        assert truncated_today(history_path, "1001") is True

    def test_renamed_known_column_is_treated_as_new_column(self, tmp_path) -> None:
        """既存列を**リネーム**した古いCSVでは、旧名の値は捨てられ、新名は空文字。

        ファイル全体マイグレーション（``history_writer._migrate_if_needed()``）
        側で吸収される挙動なので、読み込み側のテストとしては「例外を出さず、
        新 ``COLUMNS`` 順で読める（リネーム前の列は空文字）」ことを確認する。
        """
        history_path = tmp_path / "履歴.csv"
        # 「ファイル名」を「FILE_NAME」にリネームした古いバージョン
        renamed_header = ["FILE_NAME" if c == "ファイル名" else c for c in COLUMNS]
        old_values = _today_row_values()
        renamed_values = [
            "a.csv" if header == "ファイル名" else value
            for header, value in zip(COLUMNS, old_values, strict=True)
        ]
        _write_csv_raw(history_path, header=renamed_header, rows=[renamed_values])

        rows = read_history(history_path).to_rows()
        assert len(rows) == 1
        # リネーム後の列名は ``COLUMNS`` に無いため捨てる
        assert rows[0]["ファイル名"] == ""
        # 他の列は保持
        assert rows[0]["管理番号"] == "1001"


# ── 管理番号で取得済みレポートを引く読み取り関数 ───────────────────────────────
class TestReportPathAndReadReport:
    """管理番号だけをキーに、履歴から「最新の成功ファイル」を引く 2 関数。

    どちらも**履歴だけを見る**（管理表は Salesforceレポートダウンローダー側に
    あり、comken は管理表を知らない）。``report_path()`` はパスを返すか
    見つからなければ ``None`` を返し、 ``read_report()`` は同じパス
    ファイルの中身を ``Table`` で返すか見つからなければ
    ``ReportNotDownloadedError`` を投げる。テストでは ``HISTORY_PATH`` を
    ``tmp_path`` 配下に差し替え、実ファイルも一緒に作って成功／失敗の
    組み合わせを網羅する。
    """

    @pytest.fixture(autouse=True)
    def history_path(self, tmp_path, monkeypatch):
        """``paths.HISTORY_PATH`` を ``tmp_path`` の ``履歴.csv`` に差し替える。

        ``report_path()`` / ``read_report()`` は呼び出し時点で
        ``paths.HISTORY_PATH`` を読み直すため、 ``monkeypatch.setattr`` で
        差し替えれば反映される。
        """
        history_path = tmp_path / "履歴.csv"
        monkeypatch.setattr(
            "comken.services.salesforce_downloader.paths.HISTORY_PATH", history_path
        )
        yield history_path

    def _make_report_file(self, folder: Path, name: str = "1001.csv") -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / name
        path.write_text("col\nval\n", encoding="utf-8-sig")
        return path

    def test_report_path_returns_newest_success(self, history_path, tmp_path) -> None:
        """成功行が複数あるとき最新のものを返す（実行日時で降順）。"""
        entry = _entry()
        base = tmp_path / "out"
        # 古い → 新しい の順で 2 行書く
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(True, True, True, file_name="old.csv"),
            timestamp="2024-01-01 09:00:00",
            target_folder=base,
        )
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(True, True, True, file_name="new.csv"),
            timestamp="2024-01-02 09:00:00",
            target_folder=base,
        )
        self._make_report_file(base, "old.csv")
        self._make_report_file(base, "new.csv")

        assert report_path(entry.key) == base / "new.csv"

    def test_report_path_ignores_failure_rows(self, history_path, tmp_path) -> None:
        """失敗行は「最新」に含めない。

        「実装を壊して落ちる」代表例: 失敗行を除外しないと、最新の失敗で
        取れていないのに ``FileNotFoundError`` が出る／存在しないパスが
        返る事故になる。**「最新の取得が失敗のときは古い成功には遡らない」**
        という本仕様の不変条件でもある（古い成功ファイルを読んで業務側が
        古いデータで動く事故を防ぐ）。
        """
        entry = _entry()
        base = tmp_path / "out"
        # 成功 → 失敗 の順。失敗のほうが新しい時刻
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(True, True, True, file_name="ok.csv"),
            timestamp="2024-01-01 09:00:00",
            target_folder=base,
        )
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(False, False, None, file_name="ng.csv"),
            timestamp="2024-01-02 09:00:00",
            target_folder=base,
        )
        self._make_report_file(base, "ok.csv")

        # 最新の行は失敗 → 古い成功には遡らず None
        assert report_path(entry.key) is None

    def test_read_report_returns_newest_table(self, history_path, tmp_path) -> None:
        """``read_report()`` がパスを ``Table`` で返す。"""
        entry = _entry()
        base = tmp_path / "out"
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(True, True, True, file_name="x.csv"),
            target_folder=base,
        )
        self._make_report_file(base, "x.csv")

        table = read_report(entry.key)
        assert list(table.to_rows()) == [{"col": "val"}]

    def test_read_report_latest_is_failure_raises_with_failure_info(
        self, history_path, tmp_path
    ) -> None:
        """最新の取得が失敗のとき、``read_report()`` は ``ReportNotDownloadedError`` を出し、
        メッセージに失敗行の ``実行日時`` と ``エラー内容`` が入る。

        旧 ``today=True`` の挙動に似せて「最新の取得が失敗なら例外」を確かめる
        テスト。**「古い成功 → 新しい失敗」の順で、古い成功には遡らない**こと
        も同時に検証する（業務担当者のメッセージで「実行日時」と「エラー内容」を
        見て Salesforce 側の問題を判断できる形に整っているかも見る）。
        """
        entry = _entry()
        base = tmp_path / "out"
        # 古い成功 → 新しい失敗。最新の取得は失敗
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(True, True, True, file_name="yest.csv"),
            timestamp="2024-01-01 09:00:00",
            target_folder=base,
        )
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(
                succeeded=False,
                fetched_from_salesforce=False,
                saved_to_file=None,
                cause="Salesforce",
                error_code="SalesforceAuthError",
                error="資格情報が無効です",
            ),
            timestamp="2024-01-02 09:00:05",
        )

        with pytest.raises(ReportNotDownloadedError) as excinfo:
            read_report(entry.key)
        message = str(excinfo.value)
        # 失敗行の実行日時とエラー内容（原因区分 / エラーコード / エラー内容）が
        # 業務担当者に届く形になっている
        assert "2024-01-02 09:00:05" in message
        assert "Salesforce" in message
        assert "資格情報が無効です" in message

    def test_read_report_latest_failure_with_empty_timestamp_still_says_failure(
        self, history_path, tmp_path
    ) -> None:
        """失敗行の ``実行日時`` が空でも「最新の取得が失敗」の文面が出る。

        修正前は ``ReportNotDownloadedError`` が ``failed_at is not None`` で
        失敗分岐を判定しており、 ``実行日時`` が空だと ``None`` に化けて
        「取得の履歴がありません」の文面になっていた（業務担当者が
        「定期取得が止まっている」と誤認する方角に倒れる）。修正後は
        呼び出し側が ``実行日時`` が空のとき「（日時不明）」を渡す。「最新の取得が失敗」の文面が出る
        （「取得の履歴がありません」にならない）ことを確かめる。

        古い成功行を足すと ``_latest_row()`` の「``実行日時`` の降順」の比較で
        実行日時空の行が古い成功行に負けて「最新」にならない（``"" < "2024-..."``
        のため）ので、ここでは**失敗行だけ**を書き、 ``実行日時`` が空の
        失敗行が単独で「最新」になる形にする。 ``_write_row()`` は
        ``timestamp=""`` を渡すと ``now()`` にフォールバックするため、
        ``_write_csv_raw()`` で ``実行日時`` を直接空文字で書く。
        """
        entry = _entry()
        _write_csv_raw(
            history_path,
            header=list(COLUMNS),
            rows=[
                [
                    "",  # 実行日時（空）
                    entry.key,  # 管理番号
                    "",  # スケジュールキー
                    entry.summary,  # 概要
                    entry.report_id,  # レポートID
                    URL_A,  # URL
                    "P",  # プロジェクト
                    FAILURE,  # 成否
                    "",  # Salesforce取得結果
                    "",  # 保存結果
                    "",  # 保存先
                    "",  # ファイル名
                    "",  # 取得件数
                    "",  # 処理秒数
                    "Salesforce",  # 原因区分
                    "SalesforceAuthError",  # エラーコード
                    "資格情報が無効です",  # エラー内容
                    "",  # 取得経路
                ]
            ],
        )

        with pytest.raises(ReportNotDownloadedError) as excinfo:
            read_report(entry.key)
        message = str(excinfo.value)
        # 「最新の取得が失敗」の文面が出る（履歴無しではない）
        assert "が失敗しています" in message
        assert "取得の履歴がありません" not in message
        # 日時が空のときは「（日時不明）」と表示される
        assert "（日時不明）" in message
        # 失敗行の原因区分 / エラーコード / エラー内容は引き続き出る
        assert "Salesforce" in message
        assert "資格情報が無効です" in message

    def test_read_report_latest_failure_without_cause_still_says_failure(
        self, history_path, tmp_path
    ) -> None:
        """原因区分・エラーコード・エラー内容が全部空の失敗行でも「最新の取得が失敗」になる。

        ``成否 == 成功`` でも ``保存結果`` が空の行は失敗扱いだが、原因の記録は空になりうる。
        原因の有無で失敗を判定すると「取得の履歴がありません」の文面に化ける。
        """
        entry = _entry()
        _write_csv_raw(
            history_path,
            header=list(COLUMNS),
            rows=[
                [
                    "2024-01-02 09:00:05",  # 実行日時
                    entry.key,  # 管理番号
                    "",  # スケジュールキー
                    entry.summary,  # 概要
                    entry.report_id,  # レポートID
                    URL_A,  # URL
                    "P",  # プロジェクト
                    SUCCESS,  # 成否
                    SUCCESS,  # Salesforce取得結果
                    "",  # 保存結果（到達しなかった）
                    "",  # 保存先
                    "",  # ファイル名
                    "",  # 取得件数
                    "",  # 処理秒数
                    "",  # 原因区分
                    "",  # エラーコード
                    "",  # エラー内容
                    "",  # 取得経路
                ]
            ],
        )

        with pytest.raises(ReportNotDownloadedError) as excinfo:
            read_report(entry.key)
        message = str(excinfo.value)
        assert "2024-01-02 09:00:05" in message
        assert "が失敗しています" in message
        assert "取得の履歴がありません" not in message

    def test_report_path_returns_none_when_no_history_for_key(self, history_path, tmp_path) -> None:
        """該当行が無い（履歴自体が無い場合も含む）とき ``None``。"""
        entry = _entry()
        # 何も書かない
        assert report_path(entry.key) is None

    def test_report_path_returns_path_when_latest_row_is_success(
        self, history_path, tmp_path
    ) -> None:
        """最新の行が成功で実ファイルがあれば、そのパスを返す。"""
        entry = _entry()
        base = tmp_path / "out"
        today_str = now().strftime("%Y-%m-%d %H:%M:%S")
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(True, True, True, file_name="today.csv"),
            timestamp=today_str,
            target_folder=base,
        )
        self._make_report_file(base, "today.csv")

        assert report_path(entry.key) == base / "today.csv"

    def test_report_path_returns_none_when_file_missing(self, history_path, tmp_path) -> None:
        """最新の成功行はあるが実ファイルが消えていれば ``None``。

        ``report_path()`` は「ファイルが履歴を指しているか」まで含めて
        判定するため、消えているときには ``None`` を返す（``read_report()``
        が同じ条件で ``ReportNotDownloadedError`` を投げる）。
        """
        entry = _entry()
        base = tmp_path / "out"
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(True, True, True, file_name="gone.csv"),
            timestamp=now().strftime("%Y-%m-%d %H:%M:%S"),
            target_folder=base,
        )
        # ファイルは作らない

        assert report_path(entry.key) is None

    def test_report_path_does_not_read_csv_contents(self, history_path, tmp_path) -> None:
        """``report_path()`` は CSV の中身を読まない。

        履歴が指すファイルが CSV として読めないバイト列でもパスを返し、
        例外にならない。大きなレポートで CSV を読み直す無駄を排除するための
        不変条件。``read_report()`` のように ``CSV.read()`` を呼ぶと、
        ここで例外が飛んで ``report_path()`` も巻き添えで失敗するため、
        このテストは ``read_report()`` ではなく ``report_path()`` で行う。
        """
        entry = _entry()
        base = tmp_path / "out"
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(True, True, True, file_name="broken.csv"),
            timestamp=now().strftime("%Y-%m-%d %H:%M:%S"),
            target_folder=base,
        )
        # CSV として読めない中身（UTF-8 / CP932 どちらでも失敗するバイト列）
        base.mkdir(parents=True, exist_ok=True)
        broken = base / "broken.csv"
        broken.write_bytes(b"\x80\x81\x82\x83")

        # 中身を読まないため、ファイルの有無だけでパスを返す
        assert report_path(entry.key) == broken

    def test_read_report_when_record_but_file_missing_raises_with_path(
        self, history_path, tmp_path
    ) -> None:
        """記録はあるがファイルが消えていると ``read_report()`` は
        ``ReportNotDownloadedError`` を出し、メッセージに消えているパスが入る。

        ``report_path()`` も同じ条件で ``None`` を返す
        （``read_report()`` の手前でファイルの有無だけ確認できる）。
        """
        entry = _entry()
        base = tmp_path / "out"
        missing = base / "gone.csv"
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(True, True, True, file_name="gone.csv"),
            timestamp=now().strftime("%Y-%m-%d %H:%M:%S"),
            target_folder=base,
        )

        # ``report_path()`` はファイルが消えていると ``None``
        assert report_path(entry.key) is None
        # ``read_report()`` は同じ条件で ``ReportNotDownloadedError``
        with pytest.raises(ReportNotDownloadedError) as excinfo:
            read_report(entry.key)
        # メッセージに消えているパスが入っている（業務担当者が見つけられる）
        assert str(missing) in str(excinfo.value)

    def test_read_report_ignores_other_keys_partial_match(self, history_path, tmp_path) -> None:
        """別の管理番号の行を拾わない（"1001" と "10010" の部分一致に注意）。

        「実装を壊して落ちる」代表例: ``startswith`` 等で部分一致にすると、
        管理番号 "1001" を引いたつもりが "10010" の履歴を返してしまう
        （``"10010".startswith("1001")`` は True）。
        """
        base = tmp_path / "out"
        # "11001" のほうを**新しい時刻**で書いて罠にする
        _write_row(
            history_path,
            entry=_Entry(key="11001", summary="別レポート", url=URL_A),
            project="P",
            row=HistoryRow(True, True, True, file_name="other.csv"),
            timestamp=now().strftime("%Y-%m-%d %H:%M:%S"),
            target_folder=base,
        )
        self._make_report_file(base, "other.csv")

        # ``report_path()`` は ``None`` を返す
        assert report_path("1001") is None
        # ``read_report()`` は ``ReportNotDownloadedError``
        with pytest.raises(ReportNotDownloadedError):
            read_report("1001")

    def test_report_path_filters_by_schedule_key(self, history_path, tmp_path) -> None:
        """``schedule_key=`` を指定すると、そのキーの成功行のうち最新のものを返す。

        同じ管理番号でも、スケジュールキーが違う行は対象外。
        """
        entry = _entry()
        base = tmp_path / "out"
        # S0900（古い）と S1300（新しい）の両方を書く
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(True, True, True, file_name="s0900.csv", schedule_key="S0900"),
            timestamp="2024-01-01 09:00:00",
            target_folder=base,
        )
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(True, True, True, file_name="s1300.csv", schedule_key="S1300"),
            timestamp="2024-01-02 09:00:00",
            target_folder=base,
        )
        self._make_report_file(base, "s0900.csv")
        self._make_report_file(base, "s1300.csv")

        # S0900 を指定 → S0900 の行のパス
        assert report_path(entry.key, schedule_key="S0900") == base / "s0900.csv"
        # S1300 を指定 → S1300 の行のパス
        assert report_path(entry.key, schedule_key="S1300") == base / "s1300.csv"

    def test_report_path_without_schedule_key_returns_newest(self, history_path, tmp_path) -> None:
        """``schedule_key=`` を省略したときは、今までどおり最も新しい行を返す。

        「実装を壊して落ちる」代表例: 絞り込みを追加する変更で、省略時の
        挙動が「絞り込まない（最も新しい）」から変わっていないことを確かめる。
        """
        entry = _entry()
        base = tmp_path / "out"
        # S0900 のほうが古い、S1300 のほうが新しい
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(True, True, True, file_name="s0900.csv", schedule_key="S0900"),
            timestamp="2024-01-01 09:00:00",
            target_folder=base,
        )
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(True, True, True, file_name="s1300.csv", schedule_key="S1300"),
            timestamp="2024-01-02 09:00:00",
            target_folder=base,
        )
        self._make_report_file(base, "s0900.csv")
        self._make_report_file(base, "s1300.csv")

        # 省略 → 最も新しい（S1300 のほう）
        assert report_path(entry.key) == base / "s1300.csv"

    def test_report_path_schedule_key_requires_exact_match(self, history_path, tmp_path) -> None:
        """途中までの値では一致しない（完全一致、部分一致にしない）。

        「実装を壊して落ちる」代表例: ``startswith`` で部分一致にしてしまうと、
        ``"S0900".startswith("S09")`` で True になり、S0900 の行が拾われてしまう。
        """
        entry = _entry()
        base = tmp_path / "out"
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(True, True, True, file_name="s0900.csv", schedule_key="S0900"),
            timestamp=now().strftime("%Y-%m-%d %H:%M:%S"),
            target_folder=base,
        )
        self._make_report_file(base, "s0900.csv")

        # "S09" は途中まで → 一致しない（missing_path=None の ReportNotDownloadedError）
        assert report_path(entry.key, schedule_key="S09") is None
        with pytest.raises(ReportNotDownloadedError):
            read_report(entry.key, schedule_key="S09")

    def test_read_report_schedule_key_miss_includes_key_in_message(
        self, history_path, tmp_path
    ) -> None:
        """見つからないときの例外メッセージに ``schedule_key`` が含まれる。"""
        entry = _entry()
        base = tmp_path / "out"
        # S0900 の成功行だけある
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(True, True, True, file_name="s0900.csv", schedule_key="S0900"),
            timestamp=now().strftime("%Y-%m-%d %H:%M:%S"),
            target_folder=base,
        )
        self._make_report_file(base, "s0900.csv")

        with pytest.raises(ReportNotDownloadedError) as excinfo:
            read_report(entry.key, schedule_key="S1300")
        message = str(excinfo.value)
        # スケジュールキーがメッセージに入る（業務担当者が見つけやすいように）
        assert "S1300" in message
        # 「スケジュールキー S1300」のような形（括弧つき）で出る
        assert "（スケジュールキー S1300）" in message

    def test_read_report_schedule_key_miss_without_key_omits_bracket(self) -> None:
        """``schedule_key`` を指定していないときは、括弧部分が入らない。"""
        # 成功履歴なし → missing_path=None の ReportNotDownloadedError
        with pytest.raises(ReportNotDownloadedError) as excinfo:
            read_report(_entry().key)
        message = str(excinfo.value)
        # schedule_key 未指定 → 括弧部分なし
        assert "（スケジュールキー" not in message

    def test_read_report_schedule_key_miss_raises_with_key(self, history_path, tmp_path) -> None:
        """S0900 の成功行だけあるとき、S1300 を指定するとエラー（メッセージにキー入り）。

        ``read_report()`` も ``schedule_key=`` の絞り込みを尊重し、該当行が無い
        ときは ``ReportNotDownloadedError`` を投げる。スケジュールキーが
        メッセージに入って業務担当者が見つけやすい。
        """
        entry = _entry()
        base = tmp_path / "out"
        today_str = now().strftime("%Y-%m-%d %H:%M:%S")
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(True, True, True, file_name="s0900.csv", schedule_key="S0900"),
            timestamp=today_str,
            target_folder=base,
        )
        self._make_report_file(base, "s0900.csv")

        with pytest.raises(ReportNotDownloadedError) as excinfo:
            read_report(entry.key, schedule_key="S1300")
        assert "S1300" in str(excinfo.value)

    def test_report_path_filters_by_schedule_key_when_only_one_present(
        self, history_path, tmp_path
    ) -> None:
        """``report_path()`` も ``schedule_key=`` で絞り込まれる。

        S0900 の成功行だけがあるとき、S0900 を指定するとそのパス、S1300 を
        指定すると ``None``、省略すると S0900 のパスが返る。
        """
        entry = _entry()
        base = tmp_path / "out"
        today_str = now().strftime("%Y-%m-%d %H:%M:%S")
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(True, True, True, file_name="s0900.csv", schedule_key="S0900"),
            timestamp=today_str,
            target_folder=base,
        )
        self._make_report_file(base, "s0900.csv")

        # S0900 を指定 → S0900 のパス
        assert report_path(entry.key, schedule_key="S0900") == base / "s0900.csv"
        # S1300 を指定 → None（S0900 だけなので）
        assert report_path(entry.key, schedule_key="S1300") is None
        # 省略 → パス（絞り込まない）
        assert report_path(entry.key) == base / "s0900.csv"

    def test_read_report_filters_by_schedule_key(self, history_path, tmp_path) -> None:
        """``read_report()`` も ``schedule_key=`` で絞り込まれる。"""
        entry = _entry()
        base = tmp_path / "out"
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(True, True, True, file_name="s0900.csv", schedule_key="S0900"),
            timestamp="2024-01-01 09:00:00",
            target_folder=base,
        )
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(True, True, True, file_name="s1300.csv", schedule_key="S1300"),
            timestamp="2024-01-02 09:00:00",
            target_folder=base,
        )
        self._make_report_file(base, "s0900.csv")
        self._make_report_file(base, "s1300.csv")

        # S0900 を指定 → S0900 のファイル（古いほう）
        assert read_report(entry.key, schedule_key="S0900").to_rows() == [{"col": "val"}]
        # S1300 を指定 → S1300 のファイル（新しいほう）
        assert read_report(entry.key, schedule_key="S1300").to_rows() == [{"col": "val"}]

    # ── 「最新の取得が失敗なら古い成功には遡らない」不変条件 ──────────────
    # 旧実装（成功行の最新を選ぶ）では以下が成立しない。新仕様はこの5ケース
    # が成立することで「取れていないときに古いデータを黙って読まない」を担保する
    def test_report_path_oldest_success_then_newer_failure_returns_none(
        self, history_path, tmp_path
    ) -> None:
        """古い成功 → 新しい失敗 の順のとき ``report_path()`` は ``None``。

        旧実装では「最も新しい成功行のパス」を返していたため、このケースで
        古い成功ファイル（``old.csv``）が返っていた。新仕様では最新の行が
        失敗のときは遡らず ``None`` を返す（業務側が古いデータで動く事故を防ぐ）。
        """
        entry = _entry()
        base = tmp_path / "out"
        # 古い成功 → 新しい失敗
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(True, True, True, file_name="old.csv"),
            timestamp="2024-01-01 09:00:00",
            target_folder=base,
        )
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(
                succeeded=False,
                fetched_from_salesforce=False,
                saved_to_file=None,
                cause="Salesforce",
                error_code="SalesforceAuthError",
                error="資格情報が無効です",
            ),
            timestamp="2024-01-02 09:00:00",
        )
        self._make_report_file(base, "old.csv")

        # 古い成功には遡らない
        assert report_path(entry.key) is None

    def test_report_path_oldest_failure_then_newer_success_returns_newest(
        self, history_path, tmp_path
    ) -> None:
        """古い失敗 → 新しい成功 の順のとき、新しい成功のパスを返す。

        「最新が成功」の通常ケース。失敗行は無視され、新しい成功のパスが
        返る。 ``_latest_row()`` が全行を見て最新の1行を取り、その行の
        成否で ``report_path()`` が判定する。
        """
        entry = _entry()
        base = tmp_path / "out"
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(
                succeeded=False,
                fetched_from_salesforce=False,
                saved_to_file=None,
                cause="Salesforce",
                error_code="SalesforceAuthError",
                error="資格情報が無効です",
            ),
            timestamp="2024-01-01 09:00:00",
        )
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(True, True, True, file_name="new.csv"),
            timestamp="2024-01-02 09:00:00",
            target_folder=base,
        )
        self._make_report_file(base, "new.csv")

        # 新しい成功が返る（古い失敗は無視される）
        assert report_path(entry.key) == base / "new.csv"

    def test_report_path_schedule_key_ignores_failure_of_other_schedule_key(
        self, history_path, tmp_path
    ) -> None:
        """``schedule_key`` 指定時、別のスケジュールキーの新しい失敗には影響されない。

        全体としては「新しい失敗」だが、絞り込み後の最新行（指定した
        スケジュールキーの中での最新）は成功 → そのパスが返る。**別
        スケジュールキーの失敗は対象ではない**（業務ロジック上、分けて
        実行しているものを混ぜると別物の判定になる）。
        """
        entry = _entry()
        base = tmp_path / "out"
        # S0900（成功・古い）と S1300（失敗・新しい）
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(True, True, True, file_name="s0900.csv", schedule_key="S0900"),
            timestamp="2024-01-01 09:00:00",
            target_folder=base,
        )
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(
                succeeded=False,
                fetched_from_salesforce=False,
                saved_to_file=None,
                schedule_key="S1300",
                cause="Salesforce",
                error_code="SalesforceAuthError",
                error="資格情報が無効です",
            ),
            timestamp="2024-01-02 09:00:00",
        )
        self._make_report_file(base, "s0900.csv")

        # S0900 を指定 → S0900 の成功行（古い失敗は別キーなので影響しない）
        assert report_path(entry.key, schedule_key="S0900") == base / "s0900.csv"

    def test_report_path_overall_success_save_failure_is_treated_as_failure(
        self, history_path, tmp_path
    ) -> None:
        """``成否 == 成功`` でも ``保存結果 == 失敗`` の最新行は失敗扱い。

        「成否だけ成功、保存に失敗」は履歴上は「取れていない」と同じ。古い
        成功には遡らず ``None`` を返す。
        """
        entry = _entry()
        base = tmp_path / "out"
        # 古い成功 → 新しい「成否=成功 / 保存結果=失敗」
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(True, True, True, file_name="old.csv"),
            timestamp="2024-01-01 09:00:00",
            target_folder=base,
        )
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(
                succeeded=True,
                fetched_from_salesforce=True,
                saved_to_file=False,
                file_name="not-saved.csv",
                cause="ファイル",
                error_code="OSError",
                error="共有サーバー断",
            ),
            timestamp="2024-01-02 09:00:00",
            target_folder=base,
        )
        self._make_report_file(base, "old.csv")

        # 保存結果=失敗の最新行 → 古い成功には遡らず None
        assert report_path(entry.key) is None

    def test_report_path_same_timestamp_picks_later_row(self, history_path, tmp_path) -> None:
        """同じ実行日時のとき、履歴の後ろの行を採用する。

        同じ時刻で複数行あるケース（例: 同じ管理番号を同日に 2 回取得）を
        「後ろを採用」で吸収する。古い成功 → 新しい失敗 の同時刻版で、
        後ろの失敗が採用されることを確認する。
        """
        entry = _entry()
        base = tmp_path / "out"
        # 同じ実行日時で 2 行: 古い成功 → 同じ時刻の失敗
        same_timestamp = "2024-01-01 09:00:00"
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(True, True, True, file_name="old.csv"),
            timestamp=same_timestamp,
            target_folder=base,
        )
        _write_row(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(
                succeeded=False,
                fetched_from_salesforce=False,
                saved_to_file=None,
                cause="Salesforce",
                error_code="SalesforceAuthError",
                error="資格情報が無効です",
            ),
            timestamp=same_timestamp,
        )
        self._make_report_file(base, "old.csv")

        # 後ろの行（同値の採用）が失敗 → None
        assert report_path(entry.key) is None


# ── append_history ─────────────────────────────────────────────────────
class TestAppendHistory:
    """``append_history()`` の書き込み仕様の検証。

    ダウンローダー側（旧 `record()`）がやっていた「ロック → ヘッダ確認 → 追記」を
    そのまま comken 側へ持ってきた。テストでは `Mapping` で `values` を組み立て、
    期待される CSV の中身・例外・ロック中の挙動を確かめる。
    """

    def test_appends_one_row_in_columns_order(self, tmp_path) -> None:
        """``COLUMNS`` の順に1行追記され、`実行日時` は ``now()`` から作られる。"""
        history_path = tmp_path / "履歴.csv"
        append_history(
            history_path,
            {
                "管理番号": "1001",
                "スケジュールキー": "",
                "概要": "顧客一覧",
                "レポートID": "00O5g00000ABCDE",
                "URL": URL_A,
                "プロジェクト": "P",
                "成否": SUCCESS,
                "Salesforce取得結果": SUCCESS,
                "保存結果": SUCCESS,
                "保存先": str(tmp_path),
                "ファイル名": "a.csv",
                "取得件数": "1",
                "処理秒数": "0.10",
                "原因区分": "",
                "エラーコード": "",
                "エラー内容": "",
            },
        )
        table = read_history(history_path)
        assert len(table) == 1
        row = table.to_rows()[0]
        assert row["管理番号"] == "1001"
        assert row["ファイル名"] == "a.csv"
        assert row["実行日時"].startswith(now().strftime("%Y-%m-%d"))
        # 知らない列は無いこと
        assert list(row.keys()) == list(COLUMNS)

    def test_missing_columns_are_filled_with_empty(self, tmp_path) -> None:
        """``COLUMNS`` のうち ``values`` に無い列は空文字で埋められる。"""
        history_path = tmp_path / "履歴.csv"
        # 必要最小限のキーだけ渡す（不足する列は空文字で埋める）
        append_history(
            history_path,
            {
                "管理番号": "1001",
                "成否": SUCCESS,
                "ファイル名": "a.csv",
            },
        )
        row = read_history(history_path).to_rows()[0]
        # 渡さなかった列は空文字
        assert row["保存先"] == ""
        assert row["URL"] == ""
        # 渡した列は保持
        assert row["管理番号"] == "1001"
        assert row["ファイル名"] == "a.csv"

    def test_unknown_key_raises_invalid_table_input_error(self, tmp_path) -> None:
        """``COLUMNS`` に無いキーは ``InvalidTableInputError`` 相当で止める。

        タイポ・想定外の列名を早期発見できるよう、書き込みは止まる。
        """
        history_path = tmp_path / "履歴.csv"
        with pytest.raises(InvalidTableInputError):
            append_history(
                history_path,
                {
                    "管理番号": "1001",
                    "想定外の列": "x",
                },
            )

    def test_write_failure_raises_history_write_error(self, tmp_path) -> None:
        """書き込みに失敗したら ``HistoryWriteError`` で止める。

        例: 親ディレクトリが**ファイル**になっていると、その下に CSV を
        作れないので ``OSError`` が飛んで ``HistoryWriteError`` にラップされる。
        """
        blocker = tmp_path / "blocker"
        blocker.write_text("not a directory", encoding="utf-8")
        history_path = blocker / "履歴.csv"  # 親がファイルなので作れない
        with pytest.raises(HistoryWriteError):
            append_history(
                history_path,
                {"管理番号": "1001"},
            )
