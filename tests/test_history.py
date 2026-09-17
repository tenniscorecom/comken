"""ダウンロード履歴の読み取り関数を検証する。

履歴の書き込み（旧 `record()`、同時追記の排他制御を含む）は 2026-09 に comken の外
（Salesforceレポートダウンローダー）へ切り出した。書き込み側のテスト（同時追記・
書き込み時のヘッダー検証）はそちらの `tests/` にある。ここでは読み取り関数
（`successful_files_today` / `schedule_succeeded_today` / `truncated_today` /
`read_history`）だけを検証し、テストデータは `_write_row()` で直接 CSV へ書く
（`record()` が内部でやっていたことの最小限の再現）。
"""

import csv
from pathlib import Path

import pytest

from comken.core.clock import now
from comken.exceptions import HistoryHeaderMismatchError
from comken.services.salesforce_downloader.history import (
    COLUMNS,
    FAILURE,
    SUCCESS,
    HistoryRow,
    read_history,
    schedule_succeeded_today,
    successful_files_today,
    truncated_today,
)
from comken.services.salesforce_downloader.master import ReportEntry


def _write_row(path: Path, *, entry: ReportEntry, project: str, row: HistoryRow) -> None:
    """テスト用: 旧 `record()` 相当の1行をCSVへ直接書く（書き込み側は別リポジトリへ移動）。"""

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
        str(entry.folder),
        row.file_name,
        "" if row.row_count is None else row.row_count,
        f"{row.seconds:.2f}",
        row.cause,
        row.error_code,
        row.error.replace("\n", " "),
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
    entry = _entry(tmp_path)
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
    entry = _entry(tmp_path)
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
    """既存の見出しが違う場合、列ずれを読まず明示的に止める。"""
    history_path = tmp_path / "履歴.csv"
    history_path.write_text("管理番号,成否\n1000,成功\n", encoding="utf-8-sig")

    with pytest.raises(HistoryHeaderMismatchError):
        read_history(history_path)


def test_schedule_succeeded_today_returns_true_after_same_key_success(tmp_path) -> None:
    """同じスケジュールキーで当日成功した履歴があれば True を返す。"""
    history_path = tmp_path / "履歴.csv"
    entry = _entry(tmp_path)
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
    entry = _entry(tmp_path)
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
            "2024-01-01 09:00:00,1001,S001,顧客一覧,,,,成功,成功,成功,,a.csv,1,0.10,,,,"
        ),
        encoding="utf-8-sig",
    )
    assert schedule_succeeded_today(history_path, "S001") is False


def test_schedule_succeeded_today_requires_save_success(tmp_path) -> None:
    """成否=成功でも保存結果=失敗なら True にしない（保存できていないので再試行可）。"""
    history_path = tmp_path / "履歴.csv"
    entry = _entry(tmp_path)
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
    entry = _entry(tmp_path)
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
    entry = _entry(tmp_path)
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
    entry = _entry(tmp_path)
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
    entry = _entry(tmp_path)
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
            "2024-01-01 09:00:00,1001,,,,,,失敗,成功,,,"
            ",,1.00,Salesforce,SalesforceReportTruncatedError,2000 行で打ち止め"
        ),
        encoding="utf-8-sig",
    )
    assert truncated_today(history_path, "1001") is False


def test_truncated_today_ignores_successful_rows_with_same_code(tmp_path) -> None:
    """同じエラーコードの文字列が成否=成功の行に書かれていても False
    （あり得ない組合せだが、列値の照合順の防御として明示的に区別する）。"""
    history_path = tmp_path / "履歴.csv"
    entry = _entry(tmp_path)
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


def _entry(folder: Path) -> ReportEntry:
    """各テストで同じ管理表1行を使う。"""
    return ReportEntry(
        key="1001",
        group_name="営業事務グループ",
        assignee="山田",
        summary="顧客一覧",
        url="https://example.com/Report/00O5g00000ABCDE/view",
        folder=folder,
        enabled=True,
        allow_empty=False,
        note="",
    )
