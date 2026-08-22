"""Salesforce レポートの集約取得（読み取る側）を、Salesforce をモックして検証する。

`get_scheduled_report()` / `file_path_of()` は設計上ネットワークを使わない。
`download_scheduled()` で置かれたファイルを、`get_scheduled_report()` が
受け取れるかを確かめる。`service.py` を経由した書き置き（`download_scheduled`）
が必要なので、`download_scheduled` も import している（テスト専用）。

`MASTER_PATH` / `HISTORY_PATH` は `monkeypatch.setattr` で tmp_path のパスへ
差し替える。
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from comken.core.clock import today
from comken.core.table import Table
from comken.exceptions import (
    ReportDisabledError,
    ReportFileMissingError,
    ReportNotRegisteredError,
    ScheduledReportNotDownloadedError,
    ScheduledReportNotRegisteredError,
)
from comken.services.salesforce_downloader import (
    download_scheduled,
    file_path_of,
    get_scheduled_report,
    load_master,
)
from comken.services.salesforce_downloader import provider as provider_module
from comken.services.salesforce_downloader import service as service_module
from comken.toolbox.excel import Excel

URL_A = "https://example--sandbox.sandbox.my.salesforce.com/lightning/r/Report/00O5g00000ABCDE/view"
URL_B = "https://example--sandbox.sandbox.my.salesforce.com/lightning/r/Report/00O5g00000FGHIJ/view"
ROWS = [{"名前": "山田", "金額": "100"}, {"名前": "鈴木", "金額": "200"}]

HEADERS = ["ID", "概要", "Salesforce URL", "実行方式", "保存先", "有効", "備考"]


def make_master(path: Path, rows: list[list]) -> Path:
    """管理表（Excel）を作る。"""
    table_rows = [dict(zip(HEADERS, row, strict=True)) for row in rows]
    with Excel(path) as book:
        book.create_data_sheet("管理表").create_table("管理表", Table(HEADERS, table_rows))
    return path


@pytest.fixture
def paths(tmp_path, monkeypatch):
    """管理表・履歴・保存先をまとめて用意し、共有定数へ注入する。

    `_paths.MASTER_PATH` / `_paths.HISTORY_PATH` を tmp_path 配下の値へ
    差し替える。`service.py` / `provider.py` は import 時に独自のローカル束縛を
    作るので、両方の属性も同期する。
    """
    folder = tmp_path / "保存先"
    folder.mkdir()
    master = make_master(
        tmp_path / "レポート管理表.xlsx",
        [
            ["1001", "顧客一覧", URL_A, "定期", str(folder), "○", ""],
            ["1002", "売上実績", URL_B, "個別", str(folder), "○", ""],
            ["1003", "停止中", URL_B, "定期", str(folder), "×", ""],
        ],
    )
    history_path = tmp_path / "ダウンロード履歴.csv"
    monkeypatch.setattr("comken.services.salesforce_downloader._paths.MASTER_PATH", master)
    monkeypatch.setattr("comken.services.salesforce_downloader._paths.HISTORY_PATH", history_path)
    monkeypatch.setattr(service_module, "MASTER_PATH", master)
    monkeypatch.setattr(service_module, "HISTORY_PATH", history_path)
    # `provider` もローカル束縛しているので同期する
    monkeypatch.setattr(provider_module, "MASTER_PATH", master)
    monkeypatch.setattr(provider_module, "HISTORY_PATH", history_path)
    return {
        "master_path": master,
        "history_path": history_path,
        "folder": folder,
    }


def fake_salesforce(rows: list[dict] | None = None) -> MagicMock:
    """report.run() が rows を返す Salesforce クライアント。"""
    client = MagicMock()
    client.__enter__.return_value.report.run.return_value = ROWS if rows is None else rows
    site = MagicMock(return_value=client)
    return site


class TestFilePathOf:
    """file_path_of() は「管理番号_概要_日付.csv」を組み立てるだけの純関数。"""

    def test_file_name_has_key_and_summary_and_date(self, tmp_path):
        folder = tmp_path / "保存先"
        folder.mkdir()
        master = make_master(
            tmp_path / "管理表.xlsx",
            [["1001", "顧客一覧", URL_A, "定期", str(folder), "○", ""]],
        )
        entry = load_master(master)["1001"]
        stamp = today().strftime("%Y%m%d")
        assert file_path_of(entry).name == f"1001_顧客一覧_{stamp}.csv"

    def test_forbidden_characters_in_summary_are_stripped(self, tmp_path):
        """ファイル名に使えない文字（\\/:*?\"<>|）は落とす。"""
        folder = tmp_path / "保存先"
        folder.mkdir()
        master = make_master(
            tmp_path / "管理表.xlsx",
            [["1001", "禁則: A/B?C*D", URL_A, "定期", str(folder), "○", ""]],
        )
        entry = load_master(master)["1001"]
        name = file_path_of(entry).name
        # 禁則文字が含まれないこと（_ に置換されず、除去される）
        for forbidden in '\\/:*?"<>|':
            assert forbidden not in name

    def test_summary_limit_caps_long_names(self, tmp_path):
        """概要が長い場合は 30 文字で切る。"""
        folder = tmp_path / "保存先"
        folder.mkdir()
        long_summary = "あ" * 50
        master = make_master(
            tmp_path / "管理表.xlsx",
            [["1001", long_summary, URL_A, "定期", str(folder), "○", ""]],
        )
        entry = load_master(master)["1001"]
        name = file_path_of(entry).name
        # 管理番号とサフィックスを除いた概要部分が 30 文字以下
        summary_in_name = name.split("_", 1)[1].rsplit("_", 1)[0]
        assert len(summary_in_name) <= 30


class TestGetScheduledReport:
    """get_scheduled_report() は取りに行かない。"""

    def test_returns_the_file_downloaded_by_the_scheduled_run(self, paths):
        with patch(
            "comken.services.salesforce_downloader.service.site_for", return_value=fake_salesforce()
        ):
            download_scheduled("定期実行")
        reader = get_scheduled_report("1001")
        assert reader.path.is_file()
        assert reader.read_rows() == ROWS

    def test_does_not_call_salesforce(self, paths):
        with patch(
            "comken.services.salesforce_downloader.service.site_for", return_value=fake_salesforce()
        ):
            download_scheduled("定期実行")
        site = fake_salesforce()
        with patch("comken.services.salesforce_downloader.service.site_for", return_value=site):
            get_scheduled_report("1001")
        site.assert_not_called()

    def test_on_demand_report_raises(self, paths):
        """管理表で「個別」のものは、定期取得済みとして受け取れない。"""
        with pytest.raises(ScheduledReportNotRegisteredError):
            get_scheduled_report("1002")

    def test_not_downloaded_yet_raises(self, paths):
        with pytest.raises(ScheduledReportNotDownloadedError):
            get_scheduled_report("1001")

    def test_missing_file_raises_even_if_history_says_downloaded(self, paths):
        with patch(
            "comken.services.salesforce_downloader.service.site_for", return_value=fake_salesforce()
        ):
            download_scheduled("定期実行")
        file_path_of(load_master(paths["master_path"])["1001"]).unlink()
        with pytest.raises(ReportFileMissingError):
            get_scheduled_report("1001")

    def test_unregistered_key_raises(self, paths):
        with pytest.raises(ReportNotRegisteredError):
            get_scheduled_report("9999")

    def test_disabled_report_raises(self, paths):
        """無効なレポートは「定期」指定でも例外（取る前段で止める）。"""
        with pytest.raises(ReportDisabledError):
            get_scheduled_report("1003")
