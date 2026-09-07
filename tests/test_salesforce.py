"""Salesforce クライアントの配線を、HTTP をモックして検証する。"""

import contextlib
import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from comken import dry_run
from comken.exceptions import (
    CredentialNotFoundError,
    InvalidCredentialNameError,
    SalesforceAuthError,
    SalesforceBulkIngestFailedError,
    SalesforceBulkIngestTimeoutError,
    SalesforceBulkQueryFailedError,
    SalesforceBulkQueryTimeoutError,
    SalesforceConnectionError,
    SalesforceExternalIDMissingError,
    SalesforceReportAccessDeniedError,
    SalesforceReportExecutionError,
    SalesforceReportFormatError,
    SalesforceReportIDNotFoundError,
    SalesforceReportTruncatedError,
    SalesforceRequestError,
    SalesforceSiteNotFoundError,
)
from comken.toolbox.credentials import save_credentials, store
from comken.toolbox.csv import CSV
from comken.toolbox.salesforce import (
    APIMetrics,
    ClientCredentialsOAuth,
    SalesforceBase,
)
from comken.toolbox.salesforce.report import report_id_from_url
from comken.toolbox.salesforce.sites import SITES, SolutionSandbox, site_for

DOMAIN_URL = "https://example.my.salesforce.com"
INSTANCE_URL = "https://example.my.salesforce.com"
DATA_PREFIX = "/services/data/v67.0"


class _TestSalesforceBase(SalesforceBase):
    """基底クライアントの共通動作を検証するための組織クラス。"""

    DOMAIN_URL = DOMAIN_URL
    CREDENTIAL_PREFIX = "test_salesforce"
    OWNER = "test_salesforce / テスト"


class TestReportIdFromUrl:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            (
                "https://example.my.salesforce.com/lightning/r/Report/00O5g00000ABCDE/view",
                "00O5g00000ABCDE",
            ),
            (
                "https://example.my.salesforce.com/lightning/r/Report/00O5g00000ABCDEfgh/view",
                "00O5g00000ABCDEfgh",
            ),
            ("00O5g00000ABCDE", "00O5g00000ABCDE"),
            ("  00O5g00000ABCDEfgh\n", "00O5g00000ABCDEfgh"),
            (
                "https://example.my.salesforce.com/00O5g00000ABCDE",
                "00O5g00000ABCDE",
            ),
        ],
    )
    def test_extracts_only_15_or_18_character_report_id(self, text, expected):
        assert report_id_from_url(text) == expected

    @pytest.mark.parametrize(
        "text",
        [
            "https://example.my.salesforce.com/",
            "https://example.my.salesforce.com/00O1234",
            "00O5g00000ABCDEfg",
            "00O5g00000ABCDEfghi",
        ],
    )
    def test_raises_when_report_id_is_missing_or_has_an_intermediate_length(self, text):
        with pytest.raises(SalesforceReportIDNotFoundError):
            report_id_from_url(text)


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
        patch("comken.toolbox.salesforce.client.requests.Session", return_value=session),
        patch(
            "comken.toolbox.salesforce.auth.oauth_credentials.requests.post", side_effect=tokens
        ) as post,
    ):
        client = _TestSalesforceBase(
            auth=ClientCredentialsOAuth("CID", "CSECRET", DOMAIN_URL), org_name="sandbox"
        )
        yield client, session, post


class TestClientCredentialsOAuth:
    def test_posts_client_credentials_to_my_domain(self):
        """My Domain のトークンエンドポイントへ client_credentials を POST する。"""
        with patch(
            "comken.toolbox.salesforce.auth.oauth_credentials.requests.post",
            return_value=_token_response(),
        ) as post:
            token, instance_url = ClientCredentialsOAuth("CID", "CSECRET", DOMAIN_URL).fetch()

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
            "comken.toolbox.salesforce.auth.oauth_credentials.requests.post",
            return_value=_token_response(),
        ) as post:
            ClientCredentialsOAuth("CID", "CSECRET", f"{DOMAIN_URL}/").fetch()
        assert post.call_args[0][0] == f"{DOMAIN_URL}/services/oauth2/token"

    def test_auth_failure_lists_what_to_check(self):
        """認証失敗のメッセージに Run As と My Domain の確認手順が入る。"""
        with (
            patch(
                "comken.toolbox.salesforce.auth.oauth_credentials.requests.post",
                return_value=_response(400, json_body={"error": "invalid_grant"}),
            ),
            pytest.raises(SalesforceAuthError, match=r"(?s)Run As.*My Domain"),
        ):
            ClientCredentialsOAuth("CID", "CSECRET", DOMAIN_URL).fetch()

    def test_network_failure_becomes_connection_error(self):
        """通信できない場合は SalesforceConnectionError になる。"""
        with (
            patch(
                "comken.toolbox.salesforce.auth.oauth_credentials.requests.post",
                side_effect=requests.exceptions.ConnectTimeout("timed out"),
            ),
            pytest.raises(SalesforceConnectionError, match="接続できませんでした"),
        ):
            ClientCredentialsOAuth("CID", "CSECRET", DOMAIN_URL).fetch()


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

    def test_follows_absolute_next_records_url_without_prefixing_instance_url(self):
        """絶対 URL の nextRecordsUrl は instance_url を二重に付けずに辿る。"""
        next_url = f"{INSTANCE_URL}{DATA_PREFIX}/query/01g000-2000"
        page1 = _response(json_body={"records": [], "done": False, "nextRecordsUrl": next_url})
        page2 = _response(json_body={"records": [], "done": True})

        with _salesforce([page1, page2]) as (client, session, _):
            client.query("SELECT Id FROM Account")

        assert session.request.call_args_list[1][0][1] == next_url

    def test_next_records_url_on_another_host_is_not_followed(self):
        """別ホストの nextRecordsUrl へアクセストークンを送らない。

        nextRecordsUrl はレスポンス本文の値なので、書かれたホストをそのまま
        信用すると Bearer トークンを外部へ渡すことになる。
        """
        page1 = _response(
            json_body={
                "records": [],
                "done": False,
                "nextRecordsUrl": f"https://attacker.example.com{DATA_PREFIX}/query/01g000-2000",
            }
        )
        page2 = _response(json_body={"records": [], "done": True})

        with _salesforce([page1, page2]) as (client, session, _):
            client.query("SELECT Id FROM Account")

        second_url = session.request.call_args_list[1][0][1]
        assert second_url.startswith(INSTANCE_URL), "ホストは instance_url に固定する"
        assert "attacker.example.com" not in second_url

    def test_query_string_survives_url_normalization(self):
        """SOQL を載せたクエリ文字列が URL の組み立てで落ちない。"""
        with _salesforce([_response(json_body={"records": [], "done": True})]) as (
            client,
            session,
            _,
        ):
            client.query("SELECT Id FROM Account")
        assert "?q=SELECT%20Id%20FROM%20Account" in session.request.call_args[0][1]

    def test_counts_calls_per_component(self):
        """呼び出しは component ごとに数えられる。"""
        with _salesforce([_response(json_body={"records": [], "done": True})]) as (client, _, _):
            client.query("SELECT Id FROM Account")
            summary = client.metrics
        assert summary.component_stats()["query"].calls == 1

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

    def test_query_csv_saves_the_query_result(self, tmp_path):
        """query_csv() は query() と同じ結果をそのまま CSV へ保存する。"""
        response = _response(json_body={"records": [{"Id": "1", "Name": "Acme"}], "done": True})
        path = tmp_path / "result.csv"
        with _salesforce([response]) as (client, _, _):
            returned_path = client.query_csv("SELECT Id, Name FROM Account", path)
        assert returned_path == path
        with CSV(path, read_only=True) as csv_file:
            assert csv_file.read() == [{"Id": "1", "Name": "Acme"}]


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
        assert client.metrics.component_stats()["query"].retries == 1

    def test_401_on_last_transient_attempt_is_retried_once(self):
        """一時障害の最終試行で 401 になっても、新トークンで1回再送する。"""
        responses = [
            _response(500, text="Server Error"),
            _response(500, text="Server Error"),
            _response(401, text="INVALID_SESSION_ID"),
            _response(json_body={"records": [{"Id": "1"}], "done": True}),
        ]
        with (
            _salesforce(responses) as (client, session, _),
            patch("comken.toolbox.salesforce.client.time.sleep"),
        ):
            records = client.query("SELECT Id FROM Account")

        assert records == [{"Id": "1"}]
        assert session.request.call_count == 4

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
        with (
            _salesforce(responses) as (client, session, _),
            patch("comken.toolbox.salesforce.client.time.sleep") as sleep,
        ):
            records = client.query("SELECT Id FROM Account")

        assert records == [{"Id": "1"}]
        assert session.request.call_count == 2
        sleep.assert_called_once()
        assert client.metrics.component_stats()["query"].retries == 1

    def test_rate_limit_is_retried(self):
        """429 も一時的な事情として試し直す。"""
        responses = [
            _response(429, text="REQUEST_LIMIT_EXCEEDED"),
            _response(json_body={"records": [], "done": True}),
        ]
        with (
            _salesforce(responses) as (client, session, _),
            patch("comken.toolbox.salesforce.client.time.sleep"),
        ):
            client.query("SELECT Id FROM Account")
        assert session.request.call_count == 2

    def test_retries_are_bounded(self):
        """一時的な失敗が続いても無限には試さず、最後はエラーにする。"""
        responses = [_response(500, text="Server Error") for _ in range(5)]
        with (
            _salesforce(responses) as (client, session, _),
            patch("comken.toolbox.salesforce.client.time.sleep"),
            pytest.raises(SalesforceRequestError, match="HTTP 500"),
        ):
            client.query("SELECT Id FROM Account")
        assert session.request.call_count == 3, "MAX_ATTEMPTS で打ち切る"

    def test_wait_grows_with_each_attempt(self):
        """待ち時間は試行回数に比例して伸ばす。"""
        responses = [_response(500, text="Server Error") for _ in range(3)]
        with (
            _salesforce(responses) as (client, _, _),
            patch("comken.toolbox.salesforce.client.time.sleep") as sleep,
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

    def test_upsert_encodes_slash_in_external_id(self):
        """外部 ID のスラッシュを URL のパス区切りとして扱わせない。"""
        with _salesforce([_response(204)]) as (client, session, _):
            client.upsert("Account", "ExternalId__c", {"ExternalId__c": "A/1"})

        assert session.request.call_args[0][1].endswith("/ExternalId__c/A%2F1")

    def test_upsert_without_external_id_raises_specific_error(self):
        """外部 ID 不在は KeyError ではなく利用者向けの個別例外にする。"""
        with (
            _salesforce([]) as (client, session, _),
            pytest.raises(SalesforceExternalIDMissingError, match="ExternalId__c"),
        ):
            client.upsert("Account", "ExternalId__c", {"Name": "取引先"})
        session.request.assert_not_called()

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
            rows = client.report.get("00O000000000001")

        assert rows == [{"名前": "A社", "金額": "1,000"}, {"名前": "B社", "金額": "2,000"}]
        url = session.request.call_args[0][1]
        assert url == f"{INSTANCE_URL}{DATA_PREFIX}/analytics/reports/00O000000000001"

    def test_run_csv_saves_the_report_result(self, tmp_path):
        """run_csv() は get() と同じ結果をそのまま CSV へ保存する。"""
        body = _report_body([("A社", "1000")])
        path = tmp_path / "report.csv"
        with _salesforce([_response(json_body=body)]) as (client, _, _):
            returned_path = client.report.run_csv("00O000000000001", path)
        assert returned_path == path
        with CSV(path, read_only=True) as csv_file:
            assert csv_file.read() == [{"名前": "A社", "金額": "1000"}]

    def test_filters_are_posted_as_report_filters(self):
        filters = [{"column": "CREATED_DATE", "operator": "greaterThan", "value": "2026-01-01"}]
        with _salesforce([_response(json_body=_report_body([]))]) as (client, session, _):
            client.report.get("00O000000000001", filters=filters)

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
            client.report.get("00O000000000001")

    def test_truncated_report_is_recorded_in_metrics(self):
        """切り捨ては、続行した場合でも計測に残す。"""
        body = _report_body([("A社", "1")], all_data=False)
        with _salesforce([_response(json_body=body)]) as (client, _, _):
            rows = client.report.get("00O000000000001", allow_truncated=True)

        assert rows == [{"名前": "A社", "金額": "1"}]
        assert client.metrics.truncated_reports == ["00O000000000001"]

    def test_summary_report_is_rejected_explicitly(self):
        """集計形式は無言で空を返さず、明示的に弾く。"""
        body = _report_body([], report_format="SUMMARY")
        with (
            _salesforce([_response(json_body=body)]) as (client, _, _),
            pytest.raises(SalesforceReportFormatError, match=r"(?s)SUMMARY.*明細"),
        ):
            client.report.get("00O000000000001")

    def test_missing_label_falls_back_to_internal_name(self):
        """表示名が取れない列は内部名をキーにする。"""
        body = _report_body([("A社", "1")])
        body["reportExtendedMetadata"]["detailColumnInfo"] = {}
        with _salesforce([_response(json_body=body)]) as (client, _, _):
            assert client.report.get("00O000000000001") == [{"NAME": "A社", "AMOUNT": "1"}]

    def test_async_run_polls_until_success(self):
        """非同期実行は完了までポーリングして結果を返す。"""
        started = _response(json_body={"id": "0LG000000000001"})
        done = _response(json_body={**_report_body([("A社", "1")]), "status": "Success"})
        with _salesforce([started, done]) as (client, session, _):
            rows = client.report.run_async("00O000000000001")

        assert rows == [{"名前": "A社", "金額": "1"}]
        assert session.request.call_args_list[0][0][0] == "POST"
        assert session.request.call_args_list[1][0][0] == "GET"

    def test_async_run_error_raises_execution_error(self):
        """非同期実行の失敗をレポート形式エラーと混同しない。"""
        started = _response(json_body={"id": "0LG000000000001"})
        failed = _response(json_body={"status": "Error", "message": "権限がありません"})
        with (
            _salesforce([started, failed]) as (client, _, _),
            pytest.raises(SalesforceReportExecutionError, match="権限がありません"),
        ):
            client.report.run_async("00O000000000001")

    def test_describe_calls_describe_endpoint(self):
        """describe は /analytics/reports/{id}/describe を GET で叩く。"""
        body = _report_body([])
        with _salesforce([_response(json_body=body)]) as (client, session, _):
            client.report.describe("00O000000000001")

        method, url = session.request.call_args[0]
        assert method == "GET"
        assert url == f"{INSTANCE_URL}{DATA_PREFIX}/analytics/reports/00O000000000001/describe"

    def test_describe_returns_response_unchanged(self):
        """describe はレスポンス dict をそのまま返す（run() のように [{}] に畳まない）。"""
        body = _report_body([])
        with _salesforce([_response(json_body=body)]) as (client, _, _):
            described = client.report.describe("00O000000000001")

        assert described is body

    def test_describe_returns_empty_dict_when_response_is_not_dict(self):
        """describe は dict 以外のレスポンスを空 dict に丸める（_parse と同じ考え方）。"""
        with _salesforce([_response(json_body=["not", "a", "dict"])]) as (client, _, _):
            assert client.report.describe("00O000000000001") == {}

    def test_get_keeps_labels_for_zero_hit_report(self):
        """0 件ヒットのレポートでも ``get()`` は ``detailColumns`` から列を作る。

        ``rows[0]`` からの推測ではなく ``detailColumns`` / ``detailColumnInfo``
        を使うため、ヒット件数 0 でも列情報が落ちない。
        """
        body = _report_body([])
        with _salesforce([_response(json_body=body)]) as (client, _, _):
            table = client.report.get("00O000000000001")

        assert table.columns == ["名前", "金額"]


def _describe_fields_body(object_name="Opportunity", field_describe=None):
    """``describe()`` のレスポンスと Object Describe のレスポンスをまとめて返す。

    テストでは ``describe()`` のあとに ``/sobjects/{object}/describe`` が
    続けて呼ばれるため、両方をリストに並べて 1 つの ``responses`` にできる。
    """
    describe_body = {
        "reportMetadata": {
            "reportFormat": "TABULAR",
            "detailColumns": ["NAME", "AMOUNT", "STAGE_NAME", "UNKNOWN_LABEL"],
            "reportType": {"type": object_name},
        },
        "reportExtendedMetadata": {
            "detailColumnInfo": {
                "NAME": {"label": "商談名"},
                "AMOUNT": {"label": "金額"},
                "STAGE_NAME": {
                    "label": "フェーズ"
                },  # Object Describe 側に同名フィールドが2つある想定
                "UNKNOWN_LABEL": {"label": "レポート独自列"},
            }
        },
    }
    return describe_body


class TestDescribeFields:
    """``describe_fields()`` は完全な自動変換を狙わず、表示名の突き合わせだけで
    9 割を埋め、残りは「対応フィールドなし」「複数候補あり」と注記して残す。
    """

    REPORT_ID = "00O000000000001"

    def test_fills_api_name_and_type_when_label_matches(self):
        """表示名が一致する列は、実フィールドの API 名・型を埋める。"""
        describe_body = _describe_fields_body()
        object_body = {
            "fields": [
                {"name": "Name", "label": "商談名", "type": "Text"},
                {"name": "Amount", "label": "金額", "type": "Currency"},
            ]
        }
        with _salesforce(
            [_response(json_body=describe_body), _response(json_body=object_body)]
        ) as (client, _, _):
            table = client.report.describe_fields(self.REPORT_ID)

        rows = table.read_rows()
        # 一致した行は API 名・型が入り、備考は空
        assert rows[0] == {
            "列キー": "NAME",
            "表示名": "商談名",
            "対応フィールドAPI名": "Name",
            "型": "Text",
            "備考": "",
        }
        assert rows[1]["対応フィールドAPI名"] == "Amount"
        assert rows[1]["型"] == "Currency"

    def test_marks_unmatched_label_as_unknown(self):
        """一致しない表示名は API 名を ``"(不明)"`` にして対応フィールドなしと注記する。"""
        describe_body = _describe_fields_body()
        object_body = {"fields": [{"name": "Name", "label": "商談名", "type": "Text"}]}
        with _salesforce(
            [_response(json_body=describe_body), _response(json_body=object_body)]
        ) as (client, _, _):
            table = client.report.describe_fields(self.REPORT_ID)

        rows = table.read_rows()
        # AMOUNT は Object Describe に存在しない
        amount_row = next(row for row in rows if row["列キー"] == "AMOUNT")
        assert amount_row["対応フィールドAPI名"] == "(不明)"
        assert amount_row["型"] == ""
        assert amount_row["備考"] == "対応フィールドなし"

    def test_marks_multiple_candidates_without_picking_one(self):
        """同じ表示名のフィールドが複数ある列は、誤った候補を押し付けずに複数候補として残す。"""
        describe_body = _describe_fields_body()
        object_body = {
            "fields": [
                {"name": "Name", "label": "商談名", "type": "Text"},
                # 「フェーズ」を持つフィールドが2つある状況を意図的に作る
                {"name": "StageName", "label": "フェーズ", "type": "Picklist"},
                {"name": "CustomStage__c", "label": "フェーズ", "type": "Text"},
            ]
        }
        with _salesforce(
            [_response(json_body=describe_body), _response(json_body=object_body)]
        ) as (client, _, _):
            table = client.report.describe_fields(self.REPORT_ID)

        rows = table.read_rows()
        stage_row = next(row for row in rows if row["列キー"] == "STAGE_NAME")
        assert stage_row["対応フィールドAPI名"] == "(不明)"
        assert stage_row["型"] == ""
        # どちらを採るか決めかねるため、両方の候補を「API名(型)」で見せる
        assert "StageName(Picklist)" in stage_row["備考"]
        assert "CustomStage__c(Text)" in stage_row["備考"]
        assert stage_row["備考"].startswith("複数候補あり: ")

    def test_object_describe_failure_does_not_raise(self):
        """Object Describe 自体が失敗しても、例外にせず全列を「(不明)」＋理由の備考で返す。"""
        describe_body = _describe_fields_body()
        # /sobjects/.../describe が 404 を返す
        not_found = _response(404, text="NOT_FOUND")
        with _salesforce([_response(json_body=describe_body), not_found]) as (client, _, _):
            table = client.report.describe_fields(self.REPORT_ID)

        rows = table.read_rows()
        assert len(rows) == 4
        for row in rows:
            assert row["対応フィールドAPI名"] == "(不明)"
        # 理由の備考は全行同じ文言
        reasons = {row["備考"] for row in rows}
        assert len(reasons) == 1
        only_reason = reasons.pop()
        assert "Opportunity の Object Describe に失敗" in only_reason
        assert "HTTP 404" in only_reason

    def test_object_describe_401_keeps_salesforce_request_error(self):
        """Object Describe が 401 を返しても Analytics API とは別の権限系統なので、
        ``SalesforceReportAccessDeniedError`` に変換せず ``SalesforceRequestError``
        のまま送出される。
        """
        describe_body = _describe_fields_body()
        # SalesforceRequestError は _client.request が再認証を挟むので、
        # 401 が 2 回続くよう並べて再認証後の 401 を確認する
        unauthorized = _response(401, text="INVALID_SESSION_ID")
        with (
            _salesforce([_response(json_body=describe_body), unauthorized, unauthorized]) as (
                client,
                _,
                _,
            ),
            pytest.raises(SalesforceRequestError, match="HTTP 401"),
        ):
            client.report.describe_fields(self.REPORT_ID)

    def test_object_describe_403_keeps_salesforce_request_error(self):
        """403 でも同じ。Analytics API ではなくオブジェクト権限なのでレポート系に変換しない。"""
        describe_body = _describe_fields_body()
        # 403 は再認証しないので 1 個で SalesforceRequestError が出る
        forbidden = _response(403, text="INSUFFICIENT_ACCESS_OR_READONLY")
        with (
            _salesforce([_response(json_body=describe_body), forbidden]) as (client, _, _),
            pytest.raises(SalesforceRequestError, match="HTTP 403"),
        ):
            client.report.describe_fields(self.REPORT_ID)

    def test_describe_fields_csv_saves_the_table(self, tmp_path):
        """``describe_fields_csv()`` は ``describe_fields()`` と同じ結果を CSV へ保存する。"""
        describe_body = _describe_fields_body()
        object_body = {"fields": [{"name": "Name", "label": "商談名", "type": "Text"}]}
        path = tmp_path / "fields.csv"
        with _salesforce(
            [_response(json_body=describe_body), _response(json_body=object_body)]
        ) as (client, _, _):
            returned_path = client.report.describe_fields_csv(self.REPORT_ID, path)

        assert returned_path == path
        with CSV(path, read_only=True) as csv_file:
            table = csv_file.read()
        assert table.columns == ["列キー", "表示名", "対応フィールドAPI名", "型", "備考"]
        # 1 行だけ一致しているケース
        rows = table.read_rows()
        assert rows[0]["列キー"] == "NAME"
        assert rows[0]["対応フィールドAPI名"] == "Name"


class TestReportAccessDenied:
    """Reports API が 401 / 403 を返したときに限り、``SalesforceRequestError`` ではなく
    ``SalesforceReportAccessDeniedError`` に変換されることを検証する。

    文字列一致ではなく HTTP ステータスコードだけで判定する設計なので、
    500 / 400 など他のステータスは **変換されず** 元のまま送出される
    （意図せず全エラーを飲み込んでしまう変更を見逃さないため）。
    """

    REPORT_ID = "00O000000000001"

    def test_get_converts_403_to_access_denied_error(self):
        """GET の 403 は Reports API 固有の権限エラーに変換する。

        元の SalesforceRequestError の ``detail`` は新しい例外に引き継がれ、
        メッセージには ``report_id`` が含まれるので画面から追いかけられる。
        """
        with (
            _salesforce([_response(403, text="Analytics API 権限がありません")]) as (
                client,
                _,
                _,
            ),
            pytest.raises(
                SalesforceReportAccessDeniedError, match=r"(?s)HTTP 403.*00O000000000001"
            ),
        ):
            client.report.get(self.REPORT_ID)

    def test_get_converts_401_to_access_denied_error(self):
        """401 でも再認証後の 2 回目 401 がレポート系に変換される。

        ``_client.request`` は 401 を 1 回だけ再認証してやり直すので、
        ここでも 2 回連続で 401 を返すよう並べて、**再認証を挟んだ後の**
        401 が対象例外へ変換されることを確認する。
        """
        unauthorized = _response(401, text="INVALID_SESSION_ID")
        unauthorized_after_reauth = _response(401, text="INVALID_SESSION_ID")
        with (
            _salesforce([unauthorized, unauthorized_after_reauth]) as (client, _, _),
            pytest.raises(
                SalesforceReportAccessDeniedError, match=r"(?s)HTTP 401.*00O000000000001"
            ),
        ):
            client.report.get(self.REPORT_ID)

    def test_get_does_not_convert_500(self):
        """500 は権限の問題ではないのでレポート系に変換しない。

        ``SalesforceRequestError`` のまま送出され、メッセージには HTTP コードと
        元の detail が残るので、切り分けの起点が壊れない。
        5xx はリトライされるので 3 回分の 500 を用意する。
        """
        responses = [_response(500, text="Server Error") for _ in range(3)]
        with (
            _salesforce(responses) as (client, _, _),
            patch("comken.toolbox.salesforce.client.time.sleep"),
            pytest.raises(SalesforceRequestError, match=r"(?s)HTTP 500.*Server Error"),
        ):
            client.report.get(self.REPORT_ID)

    def test_get_does_not_convert_400(self):
        """400 は権限の問題ではないのでレポート系に変換しない。"""
        with (
            _salesforce([_response(400, text="INVALID_FIELD")]) as (client, _, _),
            pytest.raises(SalesforceRequestError, match="INVALID_FIELD"),
        ):
            client.report.get(self.REPORT_ID)

    def test_describe_converts_403_to_access_denied_error(self):
        """describe() も 403 で ``SalesforceReportAccessDeniedError`` に変換する。

        ``describe()`` は今までは一律 ``SalesforceRequestError`` を流していたので、
        レポート API 全体に対する権限エラーが分かりにくかった。401 / 403 は
        describe でも同じ「Reports API へのアクセス拒否」として扱う。
        """
        with (
            _salesforce([_response(403, text="Analytics API 権限がありません")]) as (
                client,
                _,
                _,
            ),
            pytest.raises(
                SalesforceReportAccessDeniedError, match=r"(?s)HTTP 403.*00O000000000001"
            ),
        ):
            client.report.describe(self.REPORT_ID)

    def test_run_async_post_converts_403_to_access_denied_error(self):
        """run_async() の POST（実行開始）でも 403 は ``SalesforceReportAccessDeniedError``
        に変換される。インスタンスを開始する前の失敗なので、ポーリングには進まない。
        """
        with (
            _salesforce([_response(403, text="Analytics API 権限がありません")]) as (
                client,
                _,
                _,
            ),
            pytest.raises(
                SalesforceReportAccessDeniedError, match=r"(?s)HTTP 403.*00O000000000001"
            ),
        ):
            client.report.run_async(self.REPORT_ID)


class TestSites:
    def test_solution_sandbox_is_a_salesforce_client(self):
        """組織クラスは共通の query / report / metrics をそのまま使える。"""
        assert issubclass(SolutionSandbox, SalesforceBase)
        auth = MagicMock()
        auth.fetch.return_value = ("TOKEN", INSTANCE_URL)
        with patch("comken.toolbox.salesforce.client.requests.Session"):
            sandbox = SolutionSandbox(auth=auth)
        assert callable(sandbox.query)
        assert sandbox.report is not None
        assert sandbox.metrics is not None

    def test_org_name_defaults_to_class_name(self):
        """計測の組織名は、指定しなければクラス名になる。"""
        session = MagicMock()
        session.headers = {}
        with (
            patch("comken.toolbox.salesforce.client.requests.Session", return_value=session),
            patch(
                "comken.toolbox.salesforce.auth.oauth_credentials.requests.post",
                return_value=_token_response(),
            ),
        ):
            site = SolutionSandbox(auth=ClientCredentialsOAuth("CID", "CSECRET", DOMAIN_URL))
        assert site.metrics.org_name == "SolutionSandbox"


class TestSiteFor:
    """レポートの URL から、つなぐ組織を決める（管理表に複数組織が混ざるため）。"""

    def test_url_of_a_registered_org(self):
        url = f"{SolutionSandbox.DOMAIN_URL}/lightning/r/Report/00O5g00000ABCDE/view"
        assert site_for(url) is SolutionSandbox

    def test_host_case_is_ignored(self):
        assert site_for(SolutionSandbox.DOMAIN_URL.upper()) is SolutionSandbox

    def test_surrounding_spaces_are_ignored(self):
        """表からコピーした値に空白が混ざっていても引ける。"""
        assert site_for(f"  {SolutionSandbox.DOMAIN_URL}/lightning  ") is SolutionSandbox

    def test_unknown_domain_raises(self):
        """未登録のドメインでは、黙って別組織へつながず止まる。"""
        with pytest.raises(SalesforceSiteNotFoundError) as error:
            site_for("https://other.my.salesforce.com/lightning/r/Report/00O5g00000ABCDE/view")
        assert SolutionSandbox.DOMAIN_URL in str(error.value)  # 登録済みの組織を案内する

    def test_report_id_alone_raises(self):
        """ID だけでは、どの組織のレポートか決められない。"""
        with pytest.raises(SalesforceSiteNotFoundError):
            site_for("00O5g00000ABCDE")

    def test_empty_raises(self):
        with pytest.raises(SalesforceSiteNotFoundError):
            site_for("")

    def test_registered_sites_are_salesforce_clients(self):
        """SITES に登録されているものは、すべて SalesforceBase の組織クラス。"""
        assert SITES
        assert all(issubclass(site, SalesforceBase) for site in SITES)


class TestCredentialsInitialization:
    """DPAPI に入れた資格情報から組み立てる経路（既定は Refresh Token Flow）。"""

    def _store(self, tmp_path):
        path = tmp_path / "system-id.enc"
        save_credentials(
            {
                "solution_sandbox_client_id": "CID",
                "solution_sandbox_client_secret": "CSECRET",
                "solution_sandbox_refresh_token": "RTOKEN",
            },
            path,
        )
        return path

    def test_uses_the_class_credential_prefix(self, tmp_path, monkeypatch):
        monkeypatch.setattr(store, "CREDENTIALS_PATH", self._store(tmp_path))
        session = MagicMock()
        session.headers = {}
        with (
            patch("comken.toolbox.salesforce.client.requests.Session", return_value=session),
            patch(
                "comken.toolbox.salesforce.auth.oauth_refresh.requests.post",
                return_value=_token_response(),
            ) as post,
        ):
            sf = SolutionSandbox()

        assert isinstance(sf, SolutionSandbox), "サブクラスのまま作られる"
        assert post.call_args.args[0] == f"{SolutionSandbox.DOMAIN_URL}/services/oauth2/token"
        assert post.call_args.kwargs["data"]["client_id"] == "CID"
        assert post.call_args.kwargs["data"]["client_secret"] == "CSECRET"

    def test_prefix_argument_switches_the_account(self, tmp_path, monkeypatch):
        """本番とテストの切り替えは、システム名を差し替えるだけで済む。"""
        path = self._store(tmp_path)
        save_credentials(
            {
                "sandbox_test_client_id": "TEST-CID",
                "sandbox_test_client_secret": "TEST-SECRET",
                "sandbox_test_refresh_token": "TEST-RTOKEN",
            },
            path,
        )
        monkeypatch.setattr(store, "CREDENTIALS_PATH", path)
        session = MagicMock()
        session.headers = {}
        with (
            patch("comken.toolbox.salesforce.client.requests.Session", return_value=session),
            patch(
                "comken.toolbox.salesforce.auth.oauth_refresh.requests.post",
                return_value=_token_response(),
            ) as post,
        ):
            SolutionSandbox(prefix="sandbox_test")

        assert post.call_args.kwargs["data"]["client_id"] == "TEST-CID"

    def test_unset_prefix_raises(self, tmp_path, monkeypatch):
        """CREDENTIAL_PREFIX を決めていない基底クラスからは作れない。"""

        class PrefixUnsetSalesforce(SalesforceBase):
            DOMAIN_URL = DOMAIN_URL
            OWNER = "test_salesforce / テスト"

        monkeypatch.setattr(store, "CREDENTIALS_PATH", self._store(tmp_path))
        with pytest.raises(InvalidCredentialNameError):
            PrefixUnsetSalesforce()

    def test_missing_credential_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(store, "CREDENTIALS_PATH", tmp_path / "system-id.enc")
        with pytest.raises(CredentialNotFoundError):
            SolutionSandbox()


class TestApiMetrics:
    def test_writes_header_once_then_appends(self, tmp_path):
        """CSV は初回だけ見出しを書き、2回目以降は追記する。"""
        path = tmp_path / "metrics.csv"
        for _ in range(2):
            metrics = APIMetrics("site_a")
            metrics.record_call("report", 0.5)
            metrics.append_csv(path)

        lines = [line for line in path.read_text(encoding="utf-8-sig").splitlines() if line]
        assert lines[0].startswith("日時,組織")
        assert len(lines) == 3, "見出し1行 + データ2行"

    def test_records_error_and_retry_counts(self):
        metrics = APIMetrics("site_a")
        metrics.record_call("crud", 0.1, is_error=True)
        metrics.record_retry("crud", "再認証")

        stat = metrics.component_stats()["crud"]
        assert (stat.calls, stat.errors, stat.retries) == (1, 1, 1)
        assert metrics.retry_reason_counts() == {"再認証": 1}

    def test_truncated_report_is_not_duplicated(self):
        metrics = APIMetrics("site_a")
        metrics.record_truncated_report("00O1")
        metrics.record_truncated_report("00O1")
        assert metrics.truncated_reports == ["00O1"]

    @pytest.mark.parametrize("limit_info", ["", "api-usage=broken", "other=1/2", "api-usage=1"])
    def test_unparsable_limit_info_is_ignored(self, limit_info):
        """解釈できないヘッダーで本処理を止めない。"""
        metrics = APIMetrics("site_a")
        metrics.update_api_usage(limit_info)
        assert metrics.api_usage is None

    def test_log_summary_reports_usage_percentage(self, caplog):
        metrics = APIMetrics("site_a")
        metrics.record_call("query", 1.0)
        metrics.update_api_usage("api-usage=1500/15000")
        with caplog.at_level("INFO"):
            metrics.log_summary()
        assert "10.0%" in caplog.text


class TestBulkQuery:
    """Bulk API 2.0 Query ジョブの配線を HTTP モックで確認する。

    各テストで、ジョブ作成 -> 状態確認（1回以上） -> 結果取得（1ページ以上）の順
    でモックレスポンスを並べる。
    """

    JOB_ID = "750xx0000000001AAA"
    SOQL = "SELECT Id, Name FROM Account"

    def _csv_response(self, text, locator="null"):
        """CSV ボディを持つモックレスポンスを作る。

        Sforce-Locator ヘッダーを locator 引数で指定できる。
        """
        return _response(
            text=text,
            headers={"Content-Type": "text/csv", "Sforce-Locator": locator},
        )

    def test_run_returns_table_for_single_page(self):
        """1 ページの通常系で、正しい Table を返せる。"""
        created = _response(json_body={"id": self.JOB_ID, "state": "UploadComplete"})
        complete = _response(json_body={"id": self.JOB_ID, "state": "JobComplete"})
        csv = self._csv_response("Id,Name\n001xx,A\n001yy,B\n")

        with (
            _salesforce([created, complete, csv]) as (client, _, _),
            patch("comken.toolbox.salesforce.bulk_query.time.sleep"),
        ):
            table = client.bulk_query.run(self.SOQL)

        assert table.columns == ["Id", "Name"]
        assert table.read_rows() == [
            {"Id": "001xx", "Name": "A"},
            {"Id": "001yy", "Name": "B"},
        ]

    def test_run_polls_until_complete(self):
        """状態確認の 1 回目が InProgress で、2 回目で JobComplete になるケースで成功する。"""
        created = _response(json_body={"id": self.JOB_ID, "state": "UploadComplete"})
        in_progress = _response(json_body={"id": self.JOB_ID, "state": "InProgress"})
        complete = _response(json_body={"id": self.JOB_ID, "state": "JobComplete"})
        csv = self._csv_response("Id\n1\n")

        with (
            _salesforce([created, in_progress, complete, csv]) as (client, _, _),
            patch("comken.toolbox.salesforce.bulk_query.time.sleep"),
        ):
            table = client.bulk_query.run(self.SOQL)

        assert table.read_rows() == [{"Id": "1"}]

    def test_run_raises_failed_error_when_job_fails(self):
        """状態確認が Failed のとき
        SalesforceBulkQueryFailedError を送出し、
        errorMessage をメッセージに含む。"""
        created = _response(json_body={"id": self.JOB_ID, "state": "UploadComplete"})
        failed = _response(
            json_body={
                "id": self.JOB_ID,
                "state": "Failed",
                "errorMessage": "SOQL 構文エラー",
            }
        )
        with (
            _salesforce([created, failed]) as (client, _, _),
            patch("comken.toolbox.salesforce.bulk_query.time.sleep"),
            pytest.raises(SalesforceBulkQueryFailedError, match="SOQL 構文エラー"),
        ):
            client.bulk_query.run(self.SOQL)

    def test_run_raises_timeout_error_when_job_stays_in_progress(self):
        """timeout_seconds を 0 にするとループに入らず SalesforceBulkQueryTimeoutError になる。"""
        created = _response(json_body={"id": self.JOB_ID, "state": "UploadComplete"})
        in_progress = _response(json_body={"id": self.JOB_ID, "state": "InProgress"})

        with (
            _salesforce([created, in_progress]) as (client, _, _),
            patch("comken.toolbox.salesforce.bulk_query.time.sleep"),
            pytest.raises(SalesforceBulkQueryTimeoutError, match=r"0 秒"),
        ):
            client.bulk_query.run(self.SOQL, timeout_seconds=0)

    def test_run_concatenates_multiple_pages_without_duplicating_header(self):
        """複数ページの結果をヘッダー行重複なく結合する。"""
        created = _response(json_body={"id": self.JOB_ID, "state": "UploadComplete"})
        complete = _response(json_body={"id": self.JOB_ID, "state": "JobComplete"})
        page1 = self._csv_response("Id,Name\n001,A\n002,B\n", locator="ABC123")
        page2 = self._csv_response("Id,Name\n003,C\n004,D\n", locator="null")

        with (
            _salesforce([created, complete, page1, page2]) as (client, _, _),
            patch("comken.toolbox.salesforce.bulk_query.time.sleep"),
        ):
            table = client.bulk_query.run(self.SOQL)

        assert table.read_rows() == [
            {"Id": "001", "Name": "A"},
            {"Id": "002", "Name": "B"},
            {"Id": "003", "Name": "C"},
            {"Id": "004", "Name": "D"},
        ]

    def test_run_returns_columns_only_for_zero_results(self):
        """0 件の場合はヘッダー行だけの CSV が返るので、列はあるが行数 0 の Table になる。"""
        created = _response(json_body={"id": self.JOB_ID, "state": "UploadComplete"})
        complete = _response(json_body={"id": self.JOB_ID, "state": "JobComplete"})
        csv = self._csv_response("Id,Name\n")

        with (
            _salesforce([created, complete, csv]) as (client, _, _),
            patch("comken.toolbox.salesforce.bulk_query.time.sleep"),
        ):
            table = client.bulk_query.run(self.SOQL)

        assert table.columns == ["Id", "Name"]
        assert table.read_rows() == []

    def test_run_csv_writes_csv_file(self, tmp_path):
        """run_csv() は run() の結果をそのまま CSV へ書き出す。"""
        created = _response(json_body={"id": self.JOB_ID, "state": "UploadComplete"})
        complete = _response(json_body={"id": self.JOB_ID, "state": "JobComplete"})
        csv = self._csv_response("Id,Name\n001,A\n")
        path = tmp_path / "bulk.csv"

        with (
            _salesforce([created, complete, csv]) as (client, _, _),
            patch("comken.toolbox.salesforce.bulk_query.time.sleep"),
        ):
            returned_path = client.bulk_query.run_csv(self.SOQL, path)

        assert returned_path == path
        with CSV(path, read_only=True) as csv_file:
            assert csv_file.read() == [
                {"Id": "001", "Name": "A"},
            ]

    def test_request_headers_argument_is_passed_to_session(self):
        """headers 引数を渡したとき、
        session.request の headers 引数にも渡される。

        1 ページ の run() で session.request が 3 回呼ばれる。
        リスト 2 回目 (result) だけ Accept: text/csv が付く。
        """
        created = _response(json_body={"id": self.JOB_ID, "state": "UploadComplete"})
        complete = _response(json_body={"id": self.JOB_ID, "state": "JobComplete"})
        csv = self._csv_response("Id\n1\n")

        with (
            _salesforce([created, complete, csv]) as (client, session, _),
            patch("comken.toolbox.salesforce.bulk_query.time.sleep"),
        ):
            client.bulk_query.run(self.SOQL)

        headers_list = [call[1].get("headers") for call in session.request.call_args_list]
        # ジョブ作成 (POST) と状態確認 (GET) は headers なし
        assert headers_list[0] is None, "ジョブ作成は headers を渡さない"
        assert headers_list[1] is None, "状態確認も headers を渡さない"
        # 結果取得 (GET) だけ CSV ヘッダーを付ける
        assert headers_list[2] == {"Accept": "text/csv"}

    def test_request_csv_returns_csv_body_and_headers(self):
        """request_csv() は CSV 文字列とレスポンスヘッダーをそのまま返す。"""
        csv = self._csv_response("Id,Name\n001,A\n", locator="XYZ999")

        with _salesforce([csv]) as (client, _, _):
            text, headers = client.request_csv(
                "GET", f"{DATA_PREFIX}/jobs/query/{self.JOB_ID}/results"
            )

        assert text == "Id,Name\n001,A\n"
        assert headers["Sforce-Locator"] == "XYZ999"


class TestBulkIngest:
    """Bulk API 2.0 Ingest ジョブの配線を HTTP モックで確認する。

    各テストで、ジョブ作成 -> アップロード -> ジョブを閉じる -> 状態確認
    (1回以上) -> 成功結果取得(1ページ以上) -> 失敗結果取得(1ページ以上) の
    順でモックレスポンスを並べる。
    """

    JOB_ID = "750xx0000000001AAA"
    OBJECT_NAME = "Account"

    def _csv_response(self, text, locator="null"):
        """CSV ボディを持つモックレスポンスを作る。

        Sforce-Locator ヘッダーを locator 引数で指定できる。
        """
        return _response(
            text=text,
            headers={"Content-Type": "text/csv", "Sforce-Locator": locator},
        )

    def _responses_for_happy_path(self, csv_text_success="sf__Id\n001\n", csv_text_fail=""):
        """成功/失敗結果とも1ページで終わる最小モックレスポンスを返す。

        ジョブ作成 -> アップロード -> ジョブを閉じる -> 状態確認(完了) ->
        成功結果 -> 失敗結果 の6個。
        """
        return [
            _response(json_body={"id": self.JOB_ID, "state": "UploadComplete"}),
            _response(204),
            _response(204),
            _response(json_body={"id": self.JOB_ID, "state": "JobComplete"}),
            self._csv_response(csv_text_success),
            self._csv_response(csv_text_fail),
        ]

    def test_insert_creates_job_with_correct_body(self):
        """insert はジョブ作成の POST body に ``operation: "insert"`` を含め、
        ``externalIdFieldName`` は**含めない**。"""
        with (
            _salesforce(self._responses_for_happy_path()) as (client, session, _),
            patch("comken.toolbox.salesforce.bulk_ingest.time.sleep"),
        ):
            result = client.bulk_ingest.insert(self.OBJECT_NAME, [{"Name": "A"}])

        # ジョブ作成 (POST /jobs/ingest) の body を確認
        create_call = session.request.call_args_list[0]
        assert create_call[0][0] == "POST"
        assert create_call[0][1] == f"{INSTANCE_URL}{DATA_PREFIX}/jobs/ingest"
        assert create_call[1]["json"] == {
            "object": self.OBJECT_NAME,
            "operation": "insert",
            "lineEnding": "LF",
            "contentType": "CSV",
        }
        assert result.state == "JobComplete"
        assert result.job_id == self.JOB_ID

    def test_upsert_creates_job_with_external_id_field(self):
        """upsert は ``externalIdFieldName`` を body に含めてジョブを作成する。"""
        with (
            _salesforce(self._responses_for_happy_path()) as (client, session, _),
            patch("comken.toolbox.salesforce.bulk_ingest.time.sleep"),
        ):
            client.bulk_ingest.upsert(self.OBJECT_NAME, "ExternalId__c", [{"ExternalId__c": "A1"}])

        assert session.request.call_args_list[0][1]["json"] == {
            "object": self.OBJECT_NAME,
            "operation": "upsert",
            "lineEnding": "LF",
            "contentType": "CSV",
            "externalIdFieldName": "ExternalId__c",
        }

    def test_delete_creates_job_with_correct_operation(self):
        """delete は ``operation: "delete"`` を body に含めてジョブを作成する。"""
        with (
            _salesforce(self._responses_for_happy_path()) as (client, session, _),
            patch("comken.toolbox.salesforce.bulk_ingest.time.sleep"),
        ):
            client.bulk_ingest.delete(self.OBJECT_NAME, [{"Id": "001xx"}])

        assert session.request.call_args_list[0][1]["json"]["operation"] == "delete"

    def test_upload_uses_text_csv_header_and_raw_data(self):
        """CSV アップロードの PUT は ``Content-Type: text/csv`` ヘッダーと
        ``json=`` ではなく ``data=`` で CSV 本文を送る。

        リクエストの順: ジョブ作成 (POST) -> アップロード (PUT) -> ジョブを閉じる (PATCH)
        なので 2 番目の call_args_list が PUT アップロード。
        """
        responses = self._responses_for_happy_path()
        with (
            _salesforce(responses) as (client, session, _),
            patch("comken.toolbox.salesforce.bulk_ingest.time.sleep"),
        ):
            client.bulk_ingest.insert(self.OBJECT_NAME, [{"Name": "A"}])

        upload_call = session.request.call_args_list[1]
        method, url = upload_call[0]
        assert (method, url) == (
            "PUT",
            f"{INSTANCE_URL}{DATA_PREFIX}/jobs/ingest/{self.JOB_ID}/batches",
        )
        # アップロードだけ CSV 用の Content-Type を上書きする
        assert upload_call[1]["headers"] == {"Content-Type": "text/csv"}
        # JSON ではなく生テキストとして送る
        assert "json" not in upload_call[1] or upload_call[1].get("json") is None
        assert isinstance(upload_call[1]["data"], str)
        # UTF-8 BOM は CSV 書き込み既定で付くので、それを除いて先頭行を確認
        body = upload_call[1]["data"]
        if body.startswith("﻿"):
            body = body[1:]
        first_line = body.splitlines()[0]
        assert first_line == "Name", "CSV 本文はヘッダー行（Name）から始まる"

    def test_failed_job_raises_with_error_message(self):
        """状態確認が ``Failed``（errorMessage 付き）なら
        ``SalesforceBulkIngestFailedError`` を送出し、メッセージに
        ``errorMessage`` の内容を含める。"""
        responses = [
            _response(json_body={"id": self.JOB_ID, "state": "UploadComplete"}),
            _response(204),  # アップロード成功
            _response(204),  # ジョブを閉じる
            _response(
                json_body={
                    "id": self.JOB_ID,
                    "state": "Failed",
                    "errorMessage": "項目 Name がありません",
                }
            ),
        ]
        with (
            _salesforce(responses) as (client, _, _),
            patch("comken.toolbox.salesforce.bulk_ingest.time.sleep"),
            pytest.raises(SalesforceBulkIngestFailedError, match="項目 Name がありません"),
        ):
            client.bulk_ingest.insert(self.OBJECT_NAME, [{"Name": "A"}])

    def test_timeout_raises_when_job_does_not_finish(self):
        """``timeout_seconds=0`` なら ``SalesforceBulkIngestTimeoutError`` になる。"""
        responses = [
            _response(json_body={"id": self.JOB_ID, "state": "UploadComplete"}),
            _response(204),  # アップロード成功
            _response(204),  # ジョブを閉じる
            _response(json_body={"id": self.JOB_ID, "state": "InProgress"}),
        ]
        with (
            _salesforce(responses) as (client, _, _),
            patch("comken.toolbox.salesforce.bulk_ingest.time.sleep"),
            pytest.raises(SalesforceBulkIngestTimeoutError, match=r"0 秒"),
        ):
            client.bulk_ingest.insert(self.OBJECT_NAME, [{"Name": "A"}], timeout_seconds=0)

    def test_failed_rows_do_not_raise(self):
        """``failedResults`` に1件以上の行が含まれていても例外にせず、
        ``BulkIngestResult.failed`` にそのまま入れる。"""
        success_csv = "sf__Id,sf__Created\n001,2024-01-01\n"
        failed_csv = "sf__Id,sf__Error\n002,項目 X が不正です\n"
        with (
            _salesforce(self._responses_for_happy_path(success_csv, failed_csv)) as (
                client,
                _,
                _,
            ),
            patch("comken.toolbox.salesforce.bulk_ingest.time.sleep"),
        ):
            result = client.bulk_ingest.insert(self.OBJECT_NAME, [{"Name": "A"}])

        assert result.successful.read_rows() == [{"sf__Id": "001", "sf__Created": "2024-01-01"}]
        assert result.failed.read_rows() == [{"sf__Id": "002", "sf__Error": "項目 X が不正です"}]

    def test_successful_results_concatenate_multiple_pages_without_duplicate_header(self):
        """``successfulResults`` が2ページに分かれるケースで、2ページ目の
        ヘッダー行を二重にせず連結する。"""
        responses = [
            _response(json_body={"id": self.JOB_ID, "state": "UploadComplete"}),
            _response(204),  # アップロード成功
            _response(204),  # ジョブを閉じる
            _response(json_body={"id": self.JOB_ID, "state": "JobComplete"}),
            self._csv_response("sf__Id\n001\n002\n", locator="ABC123"),
            self._csv_response("sf__Id\n003\n004\n", locator="null"),
            # 失敗結果は空1ページ
            self._csv_response("", locator="null"),
        ]
        with (
            _salesforce(responses) as (client, _, _),
            patch("comken.toolbox.salesforce.bulk_ingest.time.sleep"),
        ):
            result = client.bulk_ingest.insert(self.OBJECT_NAME, [{"Name": "A"}])

        assert result.successful.read_rows() == [
            {"sf__Id": "001"},
            {"sf__Id": "002"},
            {"sf__Id": "003"},
            {"sf__Id": "004"},
        ]

    def test_dry_run_does_not_send_http_and_returns_empty_result(self):
        """``dry_run()`` の中で ``insert()`` を呼ぶと実際の HTTP 呼び出しが
        1回も発生せず、空の ``BulkIngestResult`` を返す。"""
        with _salesforce([]) as (client, session, _), dry_run():
            result = client.bulk_ingest.insert(self.OBJECT_NAME, [{"Name": "A"}])

        session.request.assert_not_called()
        assert result.state == "DRY-RUN"
        assert result.job_id == ""
        assert result.successful.read_rows() == []
        assert result.failed.read_rows() == []

    def test_request_data_argument_passes_raw_text_without_json(self):
        """``SalesforceBase.request()`` に ``data="..."`` を渡すと、
        ``session.request`` の ``data=`` 引数にそのまま渡され、``json=``
        には ``None`` が渡される（``data`` を渡さない既存の経路は壊さない）。"""
        with _salesforce([_response(json_body={"records": [], "done": True})]) as (
            client,
            session,
            _,
        ):
            client.request("GET", f"{DATA_PREFIX}/limits", data="raw csv body")

        # 直近の呼び出し（query ではない data 引数付き呼び出し）を確認
        last_call = session.request.call_args_list[-1]
        assert last_call[1]["data"] == "raw csv body"
        assert last_call[1]["json"] is None
        # 既存の query() 経路は data を渡していないので影響しない（テスト冒頭の
        # query() 呼び出しは data=None のまま動いている）
