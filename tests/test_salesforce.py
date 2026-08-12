"""Salesforce クライアントの配線を、HTTP をモックして検証する。"""

import contextlib
import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from comken import dry_run
from comken.exceptions import (
    SalesforceAuthError,
    SalesforceConnectionError,
    SalesforceReportFormatError,
    SalesforceReportTruncatedError,
    SalesforceRequestError,
)
from comken.salesforce import ApiMetrics, ClientCredentialsAuth, Salesforce

DOMAIN_URL = "https://example.my.salesforce.com"
INSTANCE_URL = "https://example.my.salesforce.com"
DATA_PREFIX = "/services/data/v60.0"


def _response(status: int = 200, json_body: object = None, text: str = "", headers=None):
    """requests.Response の代わりに使うモックを作る。"""
    response = MagicMock()
    response.status_code = status
    if json_body is not None:
        response.text = text or json.dumps(json_body)
        response.headers = headers or {"Content-Type": "application/json"}
        response.json.return_value = json_body
    else:
        response.text = text
        response.headers = headers or {}
    return response


def _token_response(instance_url: str = INSTANCE_URL):
    return _response(json_body={"access_token": "TOKEN", "instance_url": instance_url})


@contextlib.contextmanager
def _salesforce(responses, token_responses=None):
    """モックした HTTP セッションを持つ Salesforce を作る。"""
    session = MagicMock()
    session.headers = {}
    session.request.side_effect = list(responses)
    tokens = list(token_responses) if token_responses else [_token_response() for _ in range(5)]
    with (
        patch("comken.salesforce.client.requests.Session", return_value=session),
        patch("comken.salesforce.oauth.requests.post", side_effect=tokens) as post,
    ):
        client = Salesforce(
            client_id="CID", client_secret="CSECRET", domain_url=DOMAIN_URL, org_name="site_a"
        )
        yield client, session, post


class TestClientCredentialsAuth:
    def test_posts_client_credentials_to_my_domain(self):
        """My Domain のトークンエンドポイントへ client_credentials を POST する。"""
        with patch(
            "comken.salesforce.oauth.requests.post", return_value=_token_response()
        ) as post:
            token, instance_url = ClientCredentialsAuth("CID", "CSECRET", DOMAIN_URL).fetch()

        assert (token, instance_url) == ("TOKEN", INSTANCE_URL)
        url, kwargs = post.call_args[0][0], post.call_args[1]
        assert url == f"{DOMAIN_URL}/services/oauth2/token"
        assert kwargs["data"] == {
            "grant_type": "client_credentials",
            "client_id": "CID",
            "client_secret": "CSECRET",
        }
        assert kwargs["timeout"] > 0, "タイムアウトを必ず指定する"

    def test_trailing_slash_in_domain_url_is_tolerated(self):
        """domain_url の末尾スラッシュがあっても URL が壊れない。"""
        with patch(
            "comken.salesforce.oauth.requests.post", return_value=_token_response()
        ) as post:
            ClientCredentialsAuth("CID", "CSECRET", f"{DOMAIN_URL}/").fetch()
        assert post.call_args[0][0] == f"{DOMAIN_URL}/services/oauth2/token"

    def test_auth_failure_lists_what_to_check(self):
        """認証失敗のメッセージに Run As と My Domain の確認手順が入る。"""
        with (
            patch(
                "comken.salesforce.oauth.requests.post",
                return_value=_response(400, json_body={"error": "invalid_grant"}),
            ),
            pytest.raises(SalesforceAuthError, match=r"(?s)Run As.*My Domain"),
        ):
            ClientCredentialsAuth("CID", "CSECRET", DOMAIN_URL).fetch()

    def test_network_failure_becomes_connection_error(self):
        """通信できない場合は SalesforceConnectionError になる。"""
        with (
            patch(
                "comken.salesforce.oauth.requests.post",
                side_effect=requests.exceptions.ConnectTimeout("timed out"),
            ),
            pytest.raises(SalesforceConnectionError, match="接続できませんでした"),
        ):
            ClientCredentialsAuth("CID", "CSECRET", DOMAIN_URL).fetch()


class TestSalesforceQuery:
    def test_sets_bearer_header_on_authentication(self):
        """認証すると Authorization ヘッダーが設定される。"""
        with _salesforce([]) as (client, session, _):
            assert session.headers["Authorization"] == "Bearer TOKEN"
            client.close()
        session.close.assert_called_once()

    def test_follows_next_records_url_and_strips_attributes(self):
        """done が偽なら次ページを辿り、attributes を落として返す。"""
        page1 = _response(
            json_body={
                "records": [{"Id": "1", "attributes": {"type": "Account"}}],
                "done": False,
                "nextRecordsUrl": f"{DATA_PREFIX}/query/01g000-2000",
            }
        )
        page2 = _response(json_body={"records": [{"Id": "2"}], "done": True})

        with _salesforce([page1, page2]) as (client, session, _):
            records = client.query("SELECT Id FROM Account")

        assert records == [{"Id": "1"}, {"Id": "2"}]
        second_url = session.request.call_args_list[1][0][1]
        assert second_url == f"{INSTANCE_URL}{DATA_PREFIX}/query/01g000-2000"

    def test_counts_calls_per_component(self):
        """呼び出しは component ごとに数えられる。"""
        with _salesforce([_response(json_body={"records": [], "done": True})]) as (client, _, _):
            client.query("SELECT Id FROM Account")
            summary = client.metrics
        assert summary._by_component["query"].calls == 1

    def test_api_usage_comes_from_response_header(self):
        """Sforce-Limit-Info から組織の API 消費量を取り込む。"""
        response = _response(
            json_body={"records": [], "done": True},
            headers={"Content-Type": "application/json", "Sforce-Limit-Info": "api-usage=42/15000"},
        )
        with _salesforce([response]) as (client, _, _):
            client.query("SELECT Id FROM Account")
        assert client.metrics.api_usage.used == 42
        assert client.metrics.api_usage.limit == 15000


class TestSalesforceReauthentication:
    def test_401_triggers_one_retry_with_new_token(self):
        """401 ならトークンを取り直して1回だけやり直す。"""
        unauthorized = _response(401, text="INVALID_SESSION_ID")
        success = _response(json_body={"records": [{"Id": "1"}], "done": True})

        with _salesforce([unauthorized, success]) as (client, session, post):
            records = client.query("SELECT Id FROM Account")

        assert records == [{"Id": "1"}]
        assert session.request.call_count == 2
        assert post.call_count == 2, "初回認証と再認証で2回トークンを取る"
        assert client.metrics._by_component["query"].retries == 1

    def test_second_401_raises_instead_of_looping(self):
        """2回続けて 401 ならリトライで隠さずエラーにする。"""
        unauthorized = [_response(401, text="INVALID_SESSION_ID") for _ in range(2)]
        with (
            _salesforce(unauthorized) as (client, session, _),
            pytest.raises(SalesforceRequestError, match="HTTP 401"),
        ):
            client.query("SELECT Id FROM Account")
        assert session.request.call_count == 2, "無限にやり直さない"

    def test_api_error_reports_method_and_path(self):
        """API エラーはメソッドとパスを添えて送出する。"""
        with (
            _salesforce([_response(400, text="INVALID_FIELD")]) as (client, _, _),
            pytest.raises(SalesforceRequestError, match=r"(?s)GET.*INVALID_FIELD"),
        ):
            client.query("SELECT Nope FROM Account")

    def test_client_error_is_not_retried(self):
        """4xx はやり直しても直らないので1回で諦める。"""
        with (
            _salesforce([_response(400, text="INVALID_FIELD")]) as (client, session, _),
            pytest.raises(SalesforceRequestError),
        ):
            client.query("SELECT Nope FROM Account")
        assert session.request.call_count == 1


class TestSalesforceTransientFailures:
    def test_server_error_is_retried_and_counted(self):
        """5xx は待って試し直し、リトライとして数える。"""
        responses = [
            _response(500, text="Server Error"),
            _response(json_body={"records": [{"Id": "1"}], "done": True}),
        ]
        with _salesforce(responses) as (client, session, _), patch(
            "comken.salesforce.client.time.sleep"
        ) as sleep:
            records = client.query("SELECT Id FROM Account")

        assert records == [{"Id": "1"}]
        assert session.request.call_count == 2
        sleep.assert_called_once()
        assert client.metrics._by_component["query"].retries == 1

    def test_rate_limit_is_retried(self):
        """429 も一時的な事情として試し直す。"""
        responses = [
            _response(429, text="REQUEST_LIMIT_EXCEEDED"),
            _response(json_body={"records": [], "done": True}),
        ]
        with _salesforce(responses) as (client, session, _), patch(
            "comken.salesforce.client.time.sleep"
        ):
            client.query("SELECT Id FROM Account")
        assert session.request.call_count == 2

    def test_retries_are_bounded(self):
        """一時的な失敗が続いても無限には試さず、最後はエラーにする。"""
        responses = [_response(500, text="Server Error") for _ in range(5)]
        with (
            _salesforce(responses) as (client, session, _),
            patch("comken.salesforce.client.time.sleep"),
            pytest.raises(SalesforceRequestError, match="HTTP 500"),
        ):
            client.query("SELECT Id FROM Account")
        assert session.request.call_count == 3, "MAX_ATTEMPTS で打ち切る"

    def test_wait_grows_with_each_attempt(self):
        """待ち時間は試行回数に比例して伸ばす。"""
        responses = [_response(500, text="Server Error") for _ in range(3)]
        with (
            _salesforce(responses) as (client, _, _),
            patch("comken.salesforce.client.time.sleep") as sleep,
            pytest.raises(SalesforceRequestError),
        ):
            client.query("SELECT Id FROM Account")
        assert [call[0][0] for call in sleep.call_args_list] == [2, 4]


class TestSalesforceCrud:
    def test_insert_returns_new_id(self):
        with _salesforce([_response(json_body={"id": "001xx", "success": True})]) as (
            client,
            session,
            _,
        ):
            record_id = client.insert("Account", {"Name": "取引先"})

        assert record_id == "001xx"
        method, url = session.request.call_args[0][0], session.request.call_args[0][1]
        assert (method, url) == ("POST", f"{INSTANCE_URL}{DATA_PREFIX}/sobjects/Account")

    def test_get_strips_attributes(self):
        body = {"Id": "001xx", "Name": "取引先", "attributes": {"type": "Account"}}
        with _salesforce([_response(json_body=body)]) as (client, _, _):
            assert client.get("Account", "001xx") == {"Id": "001xx", "Name": "取引先"}

    def test_upsert_moves_external_id_into_url(self):
        """外部 ID は URL に入れ、本文からは取り除く。"""
        with _salesforce([_response(204)]) as (client, session, _):
            client.upsert("Account", "ExternalId__c", {"ExternalId__c": "A 1", "Name": "取引先"})

        url = session.request.call_args[0][1]
        assert url.endswith("/sobjects/Account/ExternalId__c/A%201"), "値は URL エンコードする"
        assert session.request.call_args[1]["json"] == {"Name": "取引先"}

    def test_delete_sends_delete_request(self):
        with _salesforce([_response(204)]) as (client, session, _):
            client.delete("Account", "001xx")
        assert session.request.call_args[0][0] == "DELETE"

    @pytest.mark.parametrize(
        "operation",
        [
            lambda sf: sf.insert("Account", {"Name": "取引先"}),
            lambda sf: sf.update("Account", "001xx", {"Name": "取引先"}),
            lambda sf: sf.upsert("Account", "ExternalId__c", {"ExternalId__c": "A1"}),
            lambda sf: sf.delete("Account", "001xx"),
        ],
    )
    def test_dry_run_does_not_send_writes(self, operation):
        """dry-run では書き込み系のリクエストを送らない。"""
        with _salesforce([]) as (client, session, _), dry_run():
            operation(client)
        session.request.assert_not_called()

    def test_dry_run_still_allows_reads(self):
        """dry-run でも読み取りは通常どおり実行する。"""
        with (
            _salesforce([_response(json_body={"records": [{"Id": "1"}], "done": True})]) as (
                client,
                session,
                _,
            ),
            dry_run(),
        ):
            assert client.query("SELECT Id FROM Account") == [{"Id": "1"}]
        session.request.assert_called_once()


def _report_body(rows, all_data=True, report_format="TABULAR"):
    return {
        "allData": all_data,
        "reportMetadata": {"reportFormat": report_format, "detailColumns": ["NAME", "AMOUNT"]},
        "reportExtendedMetadata": {
            "detailColumnInfo": {"NAME": {"label": "名前"}, "AMOUNT": {"label": "金額"}}
        },
        "factMap": {
            "T!T": {
                "rows": [
                    {"dataCells": [{"label": name}, {"label": amount}]} for name, amount in rows
                ]
            }
        },
    }


class TestReportApi:
    def test_returns_rows_keyed_by_display_label(self):
        """列は表示名をキーにして返す。"""
        body = _report_body([("A社", "1,000"), ("B社", "2,000")])
        with _salesforce([_response(json_body=body)]) as (client, session, _):
            rows = client.report.run("00O000000000001")

        assert rows == [{"名前": "A社", "金額": "1,000"}, {"名前": "B社", "金額": "2,000"}]
        url = session.request.call_args[0][1]
        assert url == f"{INSTANCE_URL}{DATA_PREFIX}/analytics/reports/00O000000000001"

    def test_filters_are_posted_as_report_filters(self):
        filters = [{"column": "CREATED_DATE", "operator": "greaterThan", "value": "2026-01-01"}]
        with _salesforce([_response(json_body=_report_body([]))]) as (client, session, _):
            client.report.run("00O000000000001", filters=filters)

        assert session.request.call_args[0][0] == "POST"
        expected_body = {"reportMetadata": {"reportFilters": filters}}
        assert session.request.call_args[1]["json"] == expected_body

    def test_truncated_report_raises_by_default(self):
        """2000 行で切り捨てられたら既定では例外で止める。"""
        body = _report_body([("A社", "1")], all_data=False)
        with (
            _salesforce([_response(json_body=body)]) as (client, _, _),
            pytest.raises(SalesforceReportTruncatedError, match=r"(?s)2000 行.*SOQL"),
        ):
            client.report.run("00O000000000001")

    def test_truncated_report_is_recorded_in_metrics(self):
        """切り捨ては、続行した場合でも計測に残す。"""
        body = _report_body([("A社", "1")], all_data=False)
        with _salesforce([_response(json_body=body)]) as (client, _, _):
            rows = client.report.run("00O000000000001", allow_truncated=True)

        assert rows == [{"名前": "A社", "金額": "1"}]
        assert client.metrics.truncated_reports == ["00O000000000001"]

    def test_summary_report_is_rejected_explicitly(self):
        """集計形式は無言で空を返さず、明示的に弾く。"""
        body = _report_body([], report_format="SUMMARY")
        with (
            _salesforce([_response(json_body=body)]) as (client, _, _),
            pytest.raises(SalesforceReportFormatError, match=r"(?s)SUMMARY.*明細"),
        ):
            client.report.run("00O000000000001")

    def test_missing_label_falls_back_to_internal_name(self):
        """表示名が取れない列は内部名をキーにする。"""
        body = _report_body([("A社", "1")])
        body["reportExtendedMetadata"]["detailColumnInfo"] = {}
        with _salesforce([_response(json_body=body)]) as (client, _, _):
            assert client.report.run("00O000000000001") == [{"NAME": "A社", "AMOUNT": "1"}]

    def test_async_run_polls_until_success(self):
        """非同期実行は完了までポーリングして結果を返す。"""
        started = _response(json_body={"id": "0LG000000000001"})
        done = _response(json_body={**_report_body([("A社", "1")]), "status": "Success"})
        with _salesforce([started, done]) as (client, session, _):
            rows = client.report.run_async("00O000000000001")

        assert rows == [{"名前": "A社", "金額": "1"}]
        assert session.request.call_args_list[0][0][0] == "POST"
        assert session.request.call_args_list[1][0][0] == "GET"


class TestApiMetrics:
    def test_writes_header_once_then_appends(self, tmp_path):
        """CSV は初回だけ見出しを書き、2回目以降は追記する。"""
        path = tmp_path / "metrics.csv"
        for _ in range(2):
            metrics = ApiMetrics("site_a")
            metrics.record_call("report", 0.5)
            metrics.append_csv(path)

        lines = [line for line in path.read_text(encoding="utf-8-sig").splitlines() if line]
        assert lines[0].startswith("日時,組織")
        assert len(lines) == 3, "見出し1行 + データ2行"

    def test_records_error_and_retry_counts(self):
        metrics = ApiMetrics("site_a")
        metrics.record_call("crud", 0.1, is_error=True)
        metrics.record_retry("crud", "再認証")

        stat = metrics._by_component["crud"]
        assert (stat.calls, stat.errors, stat.retries) == (1, 1, 1)

    def test_truncated_report_is_not_duplicated(self):
        metrics = ApiMetrics("site_a")
        metrics.record_truncated_report("00O1")
        metrics.record_truncated_report("00O1")
        assert metrics.truncated_reports == ["00O1"]

    @pytest.mark.parametrize("limit_info", ["", "api-usage=broken", "other=1/2", "api-usage=1"])
    def test_unparsable_limit_info_is_ignored(self, limit_info):
        """解釈できないヘッダーで本処理を止めない。"""
        metrics = ApiMetrics("site_a")
        metrics.update_api_usage(limit_info)
        assert metrics.api_usage is None

    def test_log_summary_reports_usage_percentage(self, caplog):
        metrics = ApiMetrics("site_a")
        metrics.record_call("query", 1.0)
        metrics.update_api_usage("api-usage=1500/15000")
        with caplog.at_level("INFO"):
            metrics.log_summary()
        assert "10.0%" in caplog.text
