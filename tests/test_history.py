"""ダウンロード履歴の別実行単位からの同時追記を検証する。"""

from concurrent.futures import ThreadPoolExecutor
from multiprocessing import get_context
from pathlib import Path

import pytest

from comken.exceptions import HistoryHeaderMismatchError
from comken.services.salesforce_downloader.history import (
    HistoryRow,
    read_all,
    record,
    schedule_succeeded_today,
    successful_files_today,
)
from comken.services.salesforce_downloader.master import ReportEntry
from comken.toolbox.csv import CSV


def test_concurrent_appends_keep_one_header_and_complete_rows(tmp_path) -> None:
    """同時に見出し作成と追記が走っても、欠損・混在した行を作らない。"""
    history_path = tmp_path / "履歴.csv"
    entry = ReportEntry(
        key="1001",
        group_name="営業事務グループ",
        assignee="山田",
        summary="顧客一覧",
        url="https://example.com/Report/00O5g00000ABCDE/view",
        folder=tmp_path,
        enabled=True,
        allow_empty=False,
        note="",
    )

    def append(index: int) -> None:
        record(
            history_path,
            entry=entry,
            project=str(index),
            row=HistoryRow(
                succeeded=True,
                fetched_from_salesforce=True,
                saved_to_file=True,
                file_name=f"{index}.csv",
                row_count=index,
            ),
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(append, range(40)))

    with CSV(history_path) as csv_file:
        rows = csv_file.read()
    assert len(rows) == 40
    assert {row["プロジェクト"] for row in rows} == {str(index) for index in range(40)}


def test_process_appends_keep_one_header_and_complete_rows(tmp_path) -> None:
    """別プロセスから同時追記しても、見出しと各行を壊さない。"""
    history_path = tmp_path / "履歴.csv"
    arguments = [(str(history_path), str(tmp_path), index) for index in range(12)]
    with get_context("spawn").Pool(processes=4) as pool:
        pool.map(_append_from_process, arguments)

    with CSV(history_path) as csv_file:
        rows = csv_file.read()
    assert len(rows) == 12
    assert {row["プロジェクト"] for row in rows} == {str(index) for index in range(12)}


def test_rejects_history_with_different_header(tmp_path) -> None:
    """既存履歴の列が違う場合、値をずらして追記せず明示的に止める。"""
    history_path = tmp_path / "履歴.csv"
    history_path.write_text("管理番号,成否\n1000,成功\n", encoding="utf-8-sig")

    with pytest.raises(HistoryHeaderMismatchError):
        record(
            history_path,
            entry=_entry(tmp_path),
            project="追記",
            row=HistoryRow(True, True, True, file_name="new.csv"),
        )

    assert history_path.read_text(encoding="utf-8-sig").splitlines()[0] == "管理番号,成否"


def test_successful_file_requires_both_overall_and_save_success(tmp_path) -> None:
    """成否だけが成功でも、保存成功が無い履歴を取得済みにしない。"""
    history_path = tmp_path / "履歴.csv"
    entry = _entry(tmp_path)
    record(
        history_path,
        entry=entry,
        project="異常な履歴",
        row=HistoryRow(True, True, False, file_name="not-saved.csv"),
    )

    assert successful_files_today(history_path, entry.key) == []


def test_read_all_returns_every_row_in_order(tmp_path) -> None:
    """絞り込みはせず、書かれた順のまま全行を dict で返す。"""
    history_path = tmp_path / "履歴.csv"
    entry = _entry(tmp_path)
    record(
        history_path,
        entry=entry,
        project="P1",
        row=HistoryRow(True, True, True, file_name="a.csv"),
    )
    record(
        history_path,
        entry=entry,
        project="P2",
        row=HistoryRow(True, True, True, file_name="b.csv"),
    )

    rows = read_all(history_path)
    assert [row["プロジェクト"] for row in rows] == ["P1", "P2"]
    assert rows[0]["ファイル名"] == "a.csv"
    assert rows[1]["ファイル名"] == "b.csv"


def test_read_all_returns_empty_when_history_missing(tmp_path) -> None:
    """履歴が無いときは例外を出さず空リストを返す。"""
    assert read_all(tmp_path / "無い.csv") == []


def test_read_all_rejects_header_mismatch(tmp_path) -> None:
    """既存の見出しが違う場合、列ずれを読まず明示的に止める。"""
    history_path = tmp_path / "履歴.csv"
    history_path.write_text("管理番号,成否\n1000,成功\n", encoding="utf-8-sig")

    with pytest.raises(HistoryHeaderMismatchError):
        read_all(history_path)


def test_schedule_succeeded_today_returns_true_after_same_key_success(tmp_path) -> None:
    """同じスケジュールキーで当日成功した履歴があれば True を返す。"""
    history_path = tmp_path / "履歴.csv"
    entry = _entry(tmp_path)
    record(
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
    record(
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
    # まず当日分の空ファイルを作る（`record()` は内部で `now()` を使うため、
    # 直接 CSV を書いて古い日付の成功履歴を入れる）
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
    record(
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
    record(
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


def _append_from_process(arguments: tuple[str, str, int]) -> None:
    """spawnした子プロセスから履歴を1行追記する。"""
    history_path, folder, index = arguments
    record(
        history_path,
        entry=_entry(Path(folder)),
        project=str(index),
        row=HistoryRow(True, True, True, file_name=f"{index}.csv", row_count=index),
    )


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
