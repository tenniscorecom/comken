"""Salesforce レポートの集約取得を、Salesforce をモックして検証する。

管理表（Excel）と履歴（CSV）は tmp_path に本物を作り、実際に読み書きさせる。
Salesforce への通信だけを差し替える。
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from comken.exceptions import (
    DuplicateReportKeyError,
    EmptyReportError,
    InvalidReportEntryError,
    ReportDisabledError,
    ReportFileMissingError,
    ReportFolderNotFoundError,
    ReportNotRegisteredError,
    ScheduledDownloadFailedError,
    ScheduledReportNotDownloadedError,
    ScheduledReportNotRegisteredError,
)
from comken.services.salesforce_downloader import (
    download_report,
    download_scheduled,
    file_path_of,
    get_scheduled_report,
    history,
    load_master,
    shared_report_ids,
)
from comken.toolbox.csv import CsvReader
from comken.toolbox.excel import ExcelWriter
from comken.toolbox.utils.clock import today

URL_A = "https://example--sandbox.sandbox.my.salesforce.com/lightning/r/Report/00O5g00000ABCDE/view"
URL_B = "https://example--sandbox.sandbox.my.salesforce.com/lightning/r/Report/00O5g00000FGHIJ/view"
ROWS = [{"名前": "山田", "金額": "100"}, {"名前": "鈴木", "金額": "200"}]

HEADERS = ["ID", "概要", "Salesforce URL", "実行方式", "保存先", "有効"]


def make_master(path: Path, rows: list[list]) -> Path:
    """管理表（Excel）を作る。"""
    with ExcelWriter.create(path, "管理表") as book:
        sheet = book.sheet("管理表")
        sheet.write_row(1, HEADERS)
        for offset, row in enumerate(rows):
            sheet.write_row(offset + 2, row)
        book.save()
    return path


@pytest.fixture
def paths(tmp_path):
    """管理表・履歴・保存先をまとめて用意する。"""
    folder = tmp_path / "保存先"
    folder.mkdir()
    master = make_master(
        tmp_path / "レポート管理表.xlsx",
        [
            [1001, "顧客一覧", URL_A, "定期", str(folder), "有効"],
            [1002, "売上実績", URL_B, "個別", str(folder), "有効"],
            [1003, "停止中", URL_B, "定期", str(folder), "無効"],
        ],
    )
    return {
        "master_path": master,
        "history_path": tmp_path / "ダウンロード履歴.csv",
        "folder": folder,
    }


def fake_salesforce(rows: list[dict] | None = None) -> MagicMock:
    """report.run() が rows を返す Salesforce クライアント。"""
    client = MagicMock()
    client.__enter__.return_value.report.run.return_value = ROWS if rows is None else rows
    site = MagicMock(return_value=client)
    return site


class TestLoadMaster:
    """管理表の読み取りと検証。"""

    def test_reads_rows_and_extracts_report_id(self, paths):
        entries = load_master(paths["master_path"])
        assert list(entries) == [1001, 1002, 1003]
        # Salesforce のレポート ID は URL から取り出す（人には入力させない）
        assert entries[1001].report_id == "00O5g00000ABCDE"
        assert entries[1001].is_scheduled
        assert not entries[1002].is_scheduled
        assert not entries[1003].enabled

    def test_blank_rows_are_skipped(self, tmp_path):
        master = make_master(
            tmp_path / "管理表.xlsx",
            [[1001, "顧客一覧", URL_A, "定期", str(tmp_path), "有効"], [None] * 6],
        )
        assert list(load_master(master)) == [1001]

    def test_duplicate_key_raises(self, tmp_path):
        master = make_master(
            tmp_path / "管理表.xlsx",
            [
                [1001, "顧客一覧", URL_A, "定期", str(tmp_path), "有効"],
                [1001, "別の名前", URL_B, "個別", str(tmp_path), "有効"],
            ],
        )
        with pytest.raises(DuplicateReportKeyError):
            load_master(master)

    def test_url_without_report_id_raises_with_row_number(self, tmp_path):
        master = make_master(
            tmp_path / "管理表.xlsx",
            [[1001, "顧客一覧", "https://example.com/", "定期", str(tmp_path), "有効"]],
        )
        with pytest.raises(InvalidReportEntryError) as e:
            load_master(master)
        assert "2 行目" in str(e.value)  # 見出しが1行目なので、最初のデータは2行目

    def test_unknown_schedule_raises(self, tmp_path):
        master = make_master(
            tmp_path / "管理表.xlsx",
            [[1001, "顧客一覧", URL_A, "毎日", str(tmp_path), "有効"]],
        )
        with pytest.raises(InvalidReportEntryError) as e:
            load_master(master)
        assert "実行方式" in str(e.value)

    def test_non_numeric_key_raises(self, tmp_path):
        master = make_master(
            tmp_path / "管理表.xlsx",
            [["A001", "顧客一覧", URL_A, "定期", str(tmp_path), "有効"]],
        )
        with pytest.raises(InvalidReportEntryError):
            load_master(master)


class TestSharedReportIds:
    """同じ Salesforce レポートを複数の管理番号が指していることの検出。"""

    def test_detects_reports_used_by_multiple_keys(self, paths):
        entries = load_master(paths["master_path"])
        shared = shared_report_ids(entries)
        # 1002 と 1003 が同じ URL（＝同じレポート）を指している
        assert shared == {"00O5g00000FGHIJ": [1002, 1003]}

    def test_unique_reports_are_not_listed(self, tmp_path):
        master = make_master(
            tmp_path / "管理表.xlsx",
            [[1001, "顧客一覧", URL_A, "定期", str(tmp_path), "有効"]],
        )
        assert shared_report_ids(load_master(master)) == {}


class TestDownloadReport:
    """download_report() は必ず Salesforce へ取りに行く。"""

    def test_saves_file_and_returns_path(self, paths):
        with patch(
            "comken.services.salesforce_downloader.service.site_for", return_value=fake_salesforce()
        ):
            path = download_report(1001, "案件集計", **_opts(paths))
        assert path.is_file()
        assert CsvReader(path).read_rows() == ROWS

    def test_file_name_has_key_and_summary_and_date(self, paths):
        with patch(
            "comken.services.salesforce_downloader.service.site_for", return_value=fake_salesforce()
        ):
            path = download_report(1001, **_opts(paths))
        stamp = today().strftime("%Y%m%d")
        assert path.name == f"1001_顧客一覧_{stamp}.csv"

    def test_fetches_again_even_if_already_downloaded_today(self, paths):
        """今日すでに取っていても取り直す（明示的な最新取得なので）。"""
        site = fake_salesforce()
        with patch("comken.services.salesforce_downloader.service.site_for", return_value=site):
            download_report(1001, **_opts(paths))
            download_report(1001, **_opts(paths))
        assert site.return_value.__enter__.return_value.report.run.call_count == 2

    def test_unregistered_key_raises(self, paths):
        with pytest.raises(ReportNotRegisteredError):
            download_report(9999, **_opts(paths))

    def test_disabled_report_raises(self, paths):
        with pytest.raises(ReportDisabledError):
            download_report(1003, **_opts(paths))

    def test_empty_report_raises_and_saves_nothing(self, paths):
        with (
            patch(
                "comken.services.salesforce_downloader.service.site_for",
                return_value=fake_salesforce([]),
            ),
            pytest.raises(EmptyReportError),
        ):
            download_report(1001, **_opts(paths))
        assert list(paths["folder"].glob("*.csv")) == []

    def test_missing_folder_raises_and_is_not_created(self, tmp_path):
        missing = tmp_path / "無いフォルダ"
        master = make_master(
            tmp_path / "管理表.xlsx",
            [[1001, "顧客一覧", URL_A, "定期", str(missing), "有効"]],
        )
        opts = {"master_path": master, "history_path": tmp_path / "履歴.csv"}
        with (
            patch(
                "comken.services.salesforce_downloader.service.site_for",
                return_value=fake_salesforce(),
            ),
            pytest.raises(ReportFolderNotFoundError),
        ):
            download_report(1001, **opts)
        assert not missing.exists()

    def test_no_temporary_file_is_left_behind(self, paths):
        with patch(
            "comken.services.salesforce_downloader.service.site_for", return_value=fake_salesforce()
        ):
            download_report(1001, **_opts(paths))
        assert list(paths["folder"].glob("~*")) == []


class TestHistory:
    """履歴には成否も、誰が要求したかも残る。"""

    def test_success_is_recorded_with_project_and_counts(self, paths):
        with patch(
            "comken.services.salesforce_downloader.service.site_for", return_value=fake_salesforce()
        ):
            download_report(1001, "案件集計", **_opts(paths))
        row = _history_rows(paths)[-1]
        assert row["管理番号"] == "1001"
        assert row["プロジェクト"] == "案件集計"
        assert row["実行方式"] == "個別"
        assert row["成否"] == "成功"
        assert row["取得件数"] == "2"
        assert row["レポートID"] == "00O5g00000ABCDE"

    def test_failure_is_recorded(self, paths):
        with (
            patch(
                "comken.services.salesforce_downloader.service.site_for",
                return_value=fake_salesforce([]),
            ),
            pytest.raises(EmptyReportError),
        ):
            download_report(1001, "案件集計", **_opts(paths))
        row = _history_rows(paths)[-1]
        assert row["成否"] == "失敗"
        assert "0 行" in row["エラー内容"]

    def test_downloaded_today_only_counts_the_matching_trigger(self, paths):
        with patch(
            "comken.services.salesforce_downloader.service.site_for", return_value=fake_salesforce()
        ):
            download_report(1001, **_opts(paths))  # 個別として記録される
        # 個別に取っただけでは「本日の定期取得が済んだ」ことにはならない
        assert not history.downloaded_today(paths["history_path"], 1001)
        assert history.downloaded_today(paths["history_path"], 1001, history.TRIGGER_ON_DEMAND)

    def test_missing_history_file_is_not_downloaded(self, tmp_path):
        assert not history.downloaded_today(tmp_path / "無い.csv", 1001)


class TestGetScheduledReport:
    """get_scheduled_report() は取りに行かない。"""

    def test_returns_the_file_downloaded_by_the_scheduled_run(self, paths):
        with patch(
            "comken.services.salesforce_downloader.service.site_for", return_value=fake_salesforce()
        ):
            download_scheduled("定期実行", **_opts(paths))
        path = get_scheduled_report(1001, **_opts(paths))
        assert path.is_file()

    def test_does_not_call_salesforce(self, paths):
        with patch(
            "comken.services.salesforce_downloader.service.site_for", return_value=fake_salesforce()
        ):
            download_scheduled("定期実行", **_opts(paths))
        site = fake_salesforce()
        with patch("comken.services.salesforce_downloader.service.site_for", return_value=site):
            get_scheduled_report(1001, **_opts(paths))
        site.assert_not_called()

    def test_on_demand_report_raises(self, paths):
        """管理表で「個別」のものは、定期取得済みとして受け取れない。"""
        with pytest.raises(ScheduledReportNotRegisteredError):
            get_scheduled_report(1002, **_opts(paths))

    def test_not_downloaded_yet_raises(self, paths):
        with pytest.raises(ScheduledReportNotDownloadedError):
            get_scheduled_report(1001, **_opts(paths))

    def test_missing_file_raises_even_if_history_says_downloaded(self, paths):
        with patch(
            "comken.services.salesforce_downloader.service.site_for", return_value=fake_salesforce()
        ):
            download_scheduled("定期実行", **_opts(paths))
        file_path_of(load_master(paths["master_path"])[1001]).unlink()
        with pytest.raises(ReportFileMissingError):
            get_scheduled_report(1001, **_opts(paths))

    def test_unregistered_key_raises(self, paths):
        with pytest.raises(ReportNotRegisteredError):
            get_scheduled_report(9999, **_opts(paths))


class TestDownloadScheduled:
    """定期取得は「定期」かつ有効なものだけを対象にする。"""

    def test_only_enabled_scheduled_reports_are_downloaded(self, paths):
        with patch(
            "comken.services.salesforce_downloader.service.site_for", return_value=fake_salesforce()
        ):
            saved = download_scheduled(**_opts(paths))
        # 1001 だけ（1002 は個別、1003 は無効）
        assert [path.name.split("_")[0] for path in saved] == ["1001"]

    def test_one_failure_does_not_stop_the_rest(self, tmp_path):
        folder = tmp_path / "保存先"
        folder.mkdir()
        master = make_master(
            tmp_path / "管理表.xlsx",
            [
                [1001, "落ちる方", URL_A, "定期", str(tmp_path / "無い"), "有効"],
                [1002, "通る方", URL_B, "定期", str(folder), "有効"],
            ],
        )
        opts = {"master_path": master, "history_path": tmp_path / "履歴.csv"}
        with (
            patch(
                "comken.services.salesforce_downloader.service.site_for",
                return_value=fake_salesforce(),
            ),
            pytest.raises(ScheduledDownloadFailedError),
        ):
            download_scheduled(**opts)
        # 1001 で失敗しても 1002 は保存されている（続けたうえで最後に知らせる）
        assert [path.name.split("_")[0] for path in folder.glob("*.csv")] == ["1002"]

    def test_records_the_trigger_as_scheduled(self, paths):
        with patch(
            "comken.services.salesforce_downloader.service.site_for", return_value=fake_salesforce()
        ):
            download_scheduled("定期実行", **_opts(paths))
        assert _history_rows(paths)[-1]["実行方式"] == "定期"


def _opts(paths: dict) -> dict:
    return {"master_path": paths["master_path"], "history_path": paths["history_path"]}


def _history_rows(paths: dict) -> list[dict]:
    return CsvReader(paths["history_path"]).read_rows()
