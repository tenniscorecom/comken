"""SOQL レポート取得の基盤（``download_soql_reports()``）を、Salesforce をモックして検証する。

実際のレポート（サブクラス）は作らず、テスト内でダミーの ``SoqlReport`` サブクラスを
定義して使う。``SalesforceBase.query()`` をモックして Table を返す。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from comken.core.table import Table
from comken.exceptions import (
    SalesforceSiteNotFoundError,
    SoqlDownloadFailedError,
)
from comken.services.salesforce_downloader.soql_reports import _registry
from comken.services.salesforce_downloader.soql_reports import runner as runner_module
from comken.services.salesforce_downloader.soql_reports.base import SoqlReport
from comken.services.salesforce_downloader.soql_reports.runner import download_soql_reports
from comken.toolbox.csv import CSV

URL = "https://example.my.salesforce.com"
ROWS = [{"Id": "001", "Name": "山田"}, {"Id": "002", "Name": "鈴木"}]


class _DummyReport(SoqlReport):
    """``SoqlReport`` のテスト用ダミー実装。"""

    KEY = "9001"
    SUMMARY = "売上明細（テスト用）"
    URL = URL
    FOLDER = ""  # テストで上書きする

    def soql(self) -> str:
        return "SELECT Id, Name FROM Account"


class _AllowEmptyReport(SoqlReport):
    """``ALLOW_EMPTY=True`` のテスト用ダミー実装。"""

    KEY = "9002"
    SUMMARY = "空を許すレポート（テスト用）"
    URL = URL
    FOLDER = ""
    ALLOW_EMPTY = True

    def soql(self) -> str:
        return "SELECT Id FROM Account"


class _FailingReport(SoqlReport):
    """``SalesforceRequestError``（``ComkenError`` 派生）を投げるテスト用ダミー。"""

    KEY = "9003"
    SUMMARY = "失敗するレポート（テスト用）"
    URL = URL
    FOLDER = ""

    def soql(self) -> str:
        return "SELECT Id FROM Bogus"


class _EmptyReport(SoqlReport):
    """``ALLOW_EMPTY=False`` で 0 件を返すテスト用ダミー。"""

    KEY = "9004"
    SUMMARY = "空レポート（テスト用）"
    URL = URL
    FOLDER = ""

    def soql(self) -> str:
        return "SELECT Id FROM Account WHERE Id = NULL"


def fake_salesforce(rows: list[dict] | None = None) -> MagicMock:
    """``query()`` が ``Table`` を返す Salesforce クライアント。"""
    table = Table(["Id", "Name"], rows if rows is not None else ROWS)
    client = MagicMock()
    client.__enter__.return_value.query.return_value = table
    site = MagicMock(return_value=client)
    return site


def fake_empty_salesforce() -> MagicMock:
    """``query()`` が 0 行の ``Table`` を返す Salesforce クライアント。"""
    client = MagicMock()
    client.__enter__.return_value.query.return_value = Table(["Id", "Name"], [])
    site = MagicMock(return_value=client)
    return site


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    """保存先フォルダ（tmp_path 直下に1つ用意する）。"""
    target = tmp_path / "reports"
    target.mkdir()
    return target


class TestSoqlReportBase:
    """``SoqlReport`` 基底クラスの挙動確認。"""

    def test_soql_raises_not_implemented(self):
        """``soql()`` はサブクラスで実装する前提。基底のままだと ``NotImplementedError``。"""
        with pytest.raises(NotImplementedError):
            SoqlReport().soql()

    def test_default_attributes(self):
        """``KEY`` / ``SUMMARY`` / ``URL`` / ``FOLDER`` の既定値と ``ALLOW_EMPTY`` の既定値。"""
        assert SoqlReport.KEY == ""
        assert SoqlReport.SUMMARY == ""
        assert SoqlReport.URL == ""
        assert SoqlReport.FOLDER == ""
        assert SoqlReport.ALLOW_EMPTY is False


class TestDownloadSoqlReports:
    """``download_soql_reports()`` のメインシナリオ。"""

    def test_saves_csv_in_folder(self, folder):
        """取得した Table が指定フォルダへ CSV として保存される。"""
        _DummyReport.FOLDER = str(folder)
        with patch.object(runner_module, "site_for", return_value=fake_salesforce()):
            saved = download_soql_reports([_DummyReport])
        assert len(saved) == 1
        csv_path = saved[0]
        assert csv_path.is_file()
        assert csv_path.parent == folder
        with CSV(csv_path, read_only=True) as csv_file:
            assert csv_file.read().to_rows() == ROWS

    def test_uses_default_soql_reports_when_argument_is_none(self, folder):
        """``reports=None`` のときは ``SOQL_REPORTS`` が使われる。"""
        original = _registry.SOQL_REPORTS
        _DummyReport.FOLDER = str(folder)
        _registry.SOQL_REPORTS = (_DummyReport,)
        try:
            with patch.object(runner_module, "site_for", return_value=fake_salesforce()):
                saved = download_soql_reports()
            assert len(saved) == 1
        finally:
            _registry.SOQL_REPORTS = original

    def test_empty_soql_reports_returns_empty_list_when_default(self):
        """``SOQL_REPORTS`` が空タプルのときは何もせず空リストを返す。"""
        original = _registry.SOQL_REPORTS
        _registry.SOQL_REPORTS = ()
        try:
            saved = download_soql_reports()
        finally:
            _registry.SOQL_REPORTS = original
        assert saved == []

    def test_continues_after_one_failure(self, folder):
        """1件失敗しても他のレポートの取得は止めない。"""

        def query_side_effect(soql: str) -> Table:
            # ``9003`` だけ例外を投げる（SOQL 文字列で識別）。
            if "FROM Bogus" in soql:
                raise SalesforceSiteNotFoundError(URL, [URL])
            table = Table(["Id", "Name"], ROWS)
            return table

        _DummyReport.FOLDER = str(folder)
        _FailingReport.FOLDER = str(folder)
        client = MagicMock()
        client.__enter__.return_value.query.side_effect = query_side_effect
        site = MagicMock(return_value=client)
        with (
            pytest.raises(SoqlDownloadFailedError) as caught,
            patch.object(runner_module, "site_for", return_value=site),
        ):
            download_soql_reports([_DummyReport, _FailingReport])
        # 失敗したのは ``_FailingReport``（KEY="9003"）だけ
        assert caught.value.failed_keys == ["9003"]
        assert isinstance(caught.value.__cause__, SalesforceSiteNotFoundError)

    def test_raises_soql_download_failed_when_all_fail(self, folder):
        """全件失敗のときも ``SoqlDownloadFailedError`` が送出される。"""
        _DummyReport.FOLDER = str(folder)

        def query_side_effect(_soql: str) -> Table:
            raise SalesforceSiteNotFoundError(URL, [URL])

        client = MagicMock()
        client.__enter__.return_value.query.side_effect = query_side_effect
        site = MagicMock(return_value=client)
        with (
            pytest.raises(SoqlDownloadFailedError) as caught,
            patch.object(runner_module, "site_for", return_value=site),
        ):
            download_soql_reports([_DummyReport])
        assert caught.value.failed_keys == ["9001"]

    def test_propagates_unexpected_exception(self, folder):
        """想定外の例外（``TypeError`` 等）はそのまま伝播する。"""
        _DummyReport.FOLDER = str(folder)

        def query_side_effect(_soql: str) -> Table:
            raise TypeError("プログラムバグ")

        client = MagicMock()
        client.__enter__.return_value.query.side_effect = query_side_effect
        site = MagicMock(return_value=client)
        with (
            pytest.raises(TypeError),
            patch.object(runner_module, "site_for", return_value=site),
        ):
            download_soql_reports([_DummyReport])


class TestSaveSemantics:
    """``_save()`` の ``ALLOW_EMPTY`` 制御とフォルダ存在チェック。"""

    def test_empty_rows_with_allow_empty_false_raises(self, folder):
        """0 行・``ALLOW_EMPTY=False`` は ``SoqlDownloadFailedError`` に変換される。"""
        _EmptyReport.FOLDER = str(folder)
        with (
            patch.object(runner_module, "site_for", return_value=fake_empty_salesforce()),
            pytest.raises(SoqlDownloadFailedError) as caught,
        ):
            download_soql_reports([_EmptyReport])
        assert caught.value.failed_keys == ["9004"]

    def test_empty_rows_with_allow_empty_true_saves_empty_csv(self, folder):
        """0 行・``ALLOW_EMPTY=True`` は空 CSV を保存する（失敗扱いしない）。"""
        _AllowEmptyReport.FOLDER = str(folder)
        with patch.object(runner_module, "site_for", return_value=fake_empty_salesforce()):
            saved = download_soql_reports([_AllowEmptyReport])
        assert len(saved) == 1
        csv_path = saved[0]
        assert csv_path.is_file()
        with CSV(csv_path, read_only=True) as csv_file:
            table = csv_file.read()
        assert table.to_rows() == []
        # 0 行でも列は見出しとして残る（``SalesforceBase.query()`` が ``columns`` を返すため）
        assert table.columns == ["Id", "Name"]

    def test_missing_folder_raises(self, tmp_path):
        """保存先フォルダが無ければ ``SoqlDownloadFailedError`` に変換される。"""
        missing = tmp_path / "存在しないフォルダ"
        _DummyReport.FOLDER = str(missing)
        with (
            pytest.raises(SoqlDownloadFailedError) as caught,
            patch.object(runner_module, "site_for", return_value=fake_salesforce()),
        ):
            download_soql_reports([_DummyReport])
        assert caught.value.failed_keys == ["9001"]


class TestReservePath:
    """``_reserve_path()`` の連番制御（``service._reserve_path()`` と同じアルゴリズム）。"""

    def test_existing_file_does_not_get_overwritten(self, folder, monkeypatch):
        """既存ファイルと衝突したら連番（``_1`` / ``_2`` …）で別名を確保する。"""
        _DummyReport.FOLDER = str(folder)
        base_name = f"{_DummyReport.KEY}_売上明細（テスト用）_fixed.csv"
        collision = folder / base_name
        collision.write_text("既存", encoding="utf-8")
        monkeypatch.setattr(runner_module, "_file_path_of", lambda *_args, **_kwargs: collision)
        with patch.object(runner_module, "site_for", return_value=fake_salesforce()):
            saved = download_soql_reports([_DummyReport])
        # 既存ファイルは上書きされていない
        assert collision.read_text(encoding="utf-8") == "既存"
        # 別ファイルが連番付きで保存された
        assert saved[0].name == base_name.replace(".csv", "_1.csv")
        assert saved[0].is_file()

    def test_limit_exceeded_raises(self, folder, monkeypatch):
        """連番の上限に達したら ``ReportReservePathLimitError`` を内側で出し、
        ``download_soql_reports()`` が ``SoqlDownloadFailedError`` に変換する。
        """
        monkeypatch.setattr(runner_module, "RESERVE_PATH_LIMIT", 5)
        _DummyReport.FOLDER = str(folder)
        base_name = f"{_DummyReport.KEY}_売上明細（テスト用）_limit.csv"
        base = folder / base_name
        monkeypatch.setattr(runner_module, "_file_path_of", lambda *_args, **_kwargs: base)
        for sequence in range(5):
            candidate = (
                base if sequence == 0 else folder / base_name.replace(".csv", f"_{sequence}.csv")
            )
            candidate.write_text("埋まり", encoding="utf-8")
        with (
            pytest.raises(SoqlDownloadFailedError) as caught,
            patch.object(runner_module, "site_for", return_value=fake_salesforce()),
        ):
            download_soql_reports([_DummyReport])
        assert caught.value.failed_keys == ["9001"]


class TestSoqlReportsRegistry:
    """``SOQL_REPORTS`` の既定値と公開面。"""

    def test_default_is_empty_tuple(self):
        """初期状態では ``SOQL_REPORTS`` は空タプル。"""
        assert _registry.SOQL_REPORTS == ()

    def test_subclass_is_acceptable(self):
        """``SoqlReport`` 派生クラスはそのまま登録できる（型チェックが通る）。"""
        # 型注釈は実行時に強制されないが、tuple として受け入れることを確認
        items: tuple[type[SoqlReport], ...] = (_DummyReport, _AllowEmptyReport)
        assert all(issubclass(item, SoqlReport) for item in items)
