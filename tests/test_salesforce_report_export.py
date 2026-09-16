"""ReportExporter — frontdoor.jsp + 画面エクスポートでレポートを取得する経路のテスト。

実際のHTTPは飛ばさず、requests.Session をモックして配線だけを確認する
（tests/test_salesforce.py の _salesforce() と同じ方針）。
"""

from unittest.mock import MagicMock, patch

import pytest

from comken.exceptions import SalesforceReportExportError, SalesforceReportIDNotFoundError
from comken.toolbox.salesforce.report_export import ReportExporter

INSTANCE_URL = "https://example.my.salesforce.com"
REPORT_URL_1 = "https://example.my.salesforce.com/lightning/r/Report/00O5g00000ABCDE1AS/view"
REPORT_URL_2 = "https://example.my.salesforce.com/lightning/r/Report/00O5g00000ABCDE2AS/view"


def _sf(instance_url: str = INSTANCE_URL, access_token: str = "TOKEN"):
    sf = MagicMock()
    sf.instance_url = instance_url
    sf.access_token = access_token
    return sf


def _login_response():
    response = MagicMock()
    response.status_code = 200
    response.headers = {}
    return response


def _csv_response(body: bytes = b"col1,col2\n1,2\n"):
    response = MagicMock()
    response.status_code = 200
    response.headers = {
        "Content-Type": "text/csv",
        "Content-Disposition": "attachment; filename=report.csv",
    }
    response.content = body
    return response


def _html_response(status: int = 200):
    response = MagicMock()
    response.status_code = status
    response.headers = {"Content-Type": "text/html; charset=UTF-8"}
    response.content = b"<html>login</html>"
    return response


def _make_exporter(*get_side_effect):
    """frontdoor.jsp呼び出し分を先頭に足し、requests.Session をモックしたexporterを作る。"""
    session = MagicMock()
    session.get.side_effect = [_login_response(), *get_side_effect]
    with patch("comken.toolbox.salesforce.report_export.requests.Session", return_value=session):
        exporter = ReportExporter(_sf())
    return exporter, session


class TestInit:
    """__init__() — frontdoor.jsp でアクセストークンをセッションCookieに変換する。"""

    def test_calls_frontdoor_jsp_with_access_token(self):
        session = MagicMock()
        session.get.return_value = _login_response()
        with patch(
            "comken.toolbox.salesforce.report_export.requests.Session", return_value=session
        ):
            ReportExporter(_sf(access_token="MY_TOKEN"))

        session.get.assert_called_once_with(
            f"{INSTANCE_URL}/secur/frontdoor.jsp",
            params={"sid": "MY_TOKEN"},
            timeout=120,
        )


class TestExport:
    """export() — 1件のレポートをエクスポートする。"""

    def test_returns_content_when_csv(self):
        exporter, session = _make_exporter(_csv_response(b"a,b\n1,2\n"))

        content = exporter.export(REPORT_URL_1)

        assert content == b"a,b\n1,2\n"
        export_call = session.get.call_args_list[1]
        assert export_call.args[0] == f"{INSTANCE_URL}/00O5g00000ABCDE1AS"
        assert export_call.kwargs["params"] == {
            "isdtp": "p1",
            "export": "1",
            "enc": "UTF-8",
            "xf": "csv",
        }

    def test_uses_given_export_format(self):
        exporter, session = _make_exporter(_csv_response())

        exporter.export(REPORT_URL_1, export_format="xls")

        assert session.get.call_args_list[1].kwargs["params"]["xf"] == "xls"

    def test_raises_when_report_id_missing(self):
        exporter, _ = _make_exporter()

        with pytest.raises(SalesforceReportIDNotFoundError):
            exporter.export("https://example.my.salesforce.com/not-a-report")

    def test_raises_when_response_is_html(self):
        """ログイン画面が返ってきた（セッションセキュリティレベル不足の疑い）。"""
        exporter, _ = _make_exporter(_html_response())

        with pytest.raises(SalesforceReportExportError):
            exporter.export(REPORT_URL_1)

    def test_raises_when_status_not_ok(self):
        exporter, _ = _make_exporter(_html_response(status=403))

        with pytest.raises(SalesforceReportExportError):
            exporter.export(REPORT_URL_1)


class TestExportReports:
    """export_reports() — 複数レポートを並列にダウンロードして (report_id, パス) を返す。"""

    def test_downloads_all_reports_and_yields_report_id_and_path(self, tmp_path):
        exporter, _ = _make_exporter(_csv_response(b"report1"), _csv_response(b"report2"))

        results = dict(exporter.export_reports([REPORT_URL_1, REPORT_URL_2], tmp_path))

        assert set(results) == {"00O5g00000ABCDE1AS", "00O5g00000ABCDE2AS"}
        for report_id, path in results.items():
            assert path == tmp_path / f"{report_id}.csv"
            assert path.exists()

    def test_creates_target_directory(self, tmp_path):
        exporter, _ = _make_exporter(_csv_response())

        target = tmp_path / "nested" / "dir"
        list(exporter.export_reports([REPORT_URL_1], target))

        assert target.is_dir()

    def test_raises_when_one_report_fails(self, tmp_path):
        exporter, _ = _make_exporter(_html_response())

        with pytest.raises(SalesforceReportExportError):
            list(exporter.export_reports([REPORT_URL_1], tmp_path))
