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
    SalesforceConnectionError,
    SalesforceExternalIdMissingError,
    SalesforceReportExecutionError,
    SalesforceReportFormatError,
    SalesforceReportIdNotFoundError,
    SalesforceReportTruncatedError,
    SalesforceRequestError,
    SalesforceSiteNotFoundError,
)
from comken.toolbox.credentials import save_credentials, store
from comken.toolbox.salesforce import (
    ApiMetrics,
    ClientCredentialsAuth,
    SalesforceBase,
    report_id_from_url,
)
from comken.toolbox.salesforce.sites import SITES, Sandbox, site_for

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
        with pytest.raises(SalesforceReportIdNotFoundError):
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
            "comken.toolbox.salesforce.oauth_credentials.requests.post", side_effect=tokens
        ) as post,
    ):
        client = _TestSalesforceBase(
            auth=ClientCredentialsAuth("CID", "CSECRET", DOMAIN_URL), org_name="sandbox"
        )
        yield client, session, post


class TestClientCredentialsAuth:
    def test_posts_client_credentials_to_my_domain(self):
        """My Domain のトークンエンドポイントへ client_credentials を POST する。"""
        with patch(
            "comken.toolbox.salesforce.oauth_credentials.requests.post",
            return_value=_token_response(),
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
            "comken.toolbox.salesforce.oauth_credentials.requests.post",
            return_value=_token_response(),
        ) as post:
            ClientCredentialsAuth("CID", "CSECRET", f"{DOMAIN_URL}/").fetch()
        assert post.call_args[0][0] == f"{DOMAIN_URL}/services/oauth2/token"

    def test_auth_failure_lists_what_to_check(self):
        """認証失敗のメッセージに Run As と My Domain の確認手順が入る。"""
        with (
            patch(
                "comken.toolbox.salesforce.oauth_credentials.requests.post",
                return_value=_response(400, json_body={"error": "invalid_grant"}),
            ),
            pytest.raises(SalesforceAuthError, match=r"(?s)Run As.*My Domain"),
        ):
            ClientCredentialsAuth("CID", "CSECRET", DOMAIN_URL).fetch()

    def test_network_failure_becomes_connection_error(self):
        """通信できない場合は SalesforceConnectionError になる。"""
        with (
            patch(
                "comken.toolbox.salesforce.oauth_credentials.requests.post",
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
            pytest.raises(SalesforceExternalIdMissingError, match="ExternalId__c"),
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

    def test_async_run_error_raises_execution_error(self):
        """非同期実行の失敗をレポート形式エラーと混同しない。"""
        started = _response(json_body={"id": "0LG000000000001"})
        failed = _response(json_body={"status": "Error", "message": "権限がありません"})
        with (
            _salesforce([started, failed]) as (client, _, _),
            pytest.raises(SalesforceReportExecutionError, match="権限がありません"),
        ):
            client.report.run_async("00O000000000001")


class TestSites:
    def test_sandbox_is_a_salesforce_client(self):
        """組織クラスは共通の query / report / metrics をそのまま使える。"""
        assert issubclass(Sandbox, SalesforceBase)
        auth = MagicMock()
        auth.fetch.return_value = ("TOKEN", INSTANCE_URL)
        with patch("comken.toolbox.salesforce.client.requests.Session"):
            sandbox = Sandbox(auth=auth)
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
                "comken.toolbox.salesforce.oauth_credentials.requests.post",
                return_value=_token_response(),
            ),
        ):
            site = Sandbox(auth=ClientCredentialsAuth("CID", "CSECRET", DOMAIN_URL))
        assert site.metrics.org_name == "Sandbox"

    def test_site_report_uses_its_own_report_id(self):
        """組織固有のレポート ID がそのまま URL に載る。"""
        session = MagicMock()
        session.headers = {}
        session.request.side_effect = [_response(json_body=_report_body([("A社", "1")]))]
        with (
            patch("comken.toolbox.salesforce.client.requests.Session", return_value=session),
            patch(
                "comken.toolbox.salesforce.oauth_credentials.requests.post",
                return_value=_token_response(),
            ),
            Sandbox(auth=ClientCredentialsAuth("CID", "CSECRET", DOMAIN_URL)) as sf,
        ):
            rows = sf.opportunities()

        assert rows == [{"名前": "A社", "金額": "1"}]
        assert session.request.call_args[0][1].endswith(f"/{Sandbox.REPORT_OPPORTUNITIES}")


class TestSiteFor:
    """レポートの URL から、つなぐ組織を決める（管理表に複数組織が混ざるため）。"""

    def test_url_of_a_registered_org(self):
        url = f"{Sandbox.DOMAIN_URL}/lightning/r/Report/00O5g00000ABCDE/view"
        assert site_for(url) is Sandbox

    def test_host_case_is_ignored(self):
        assert site_for(Sandbox.DOMAIN_URL.upper()) is Sandbox

    def test_surrounding_spaces_are_ignored(self):
        """表からコピーした値に空白が混ざっていても引ける。"""
        assert site_for(f"  {Sandbox.DOMAIN_URL}/lightning  ") is Sandbox

    def test_unknown_domain_raises(self):
        """未登録のドメインでは、黙って別組織へつながず止まる。"""
        with pytest.raises(SalesforceSiteNotFoundError) as error:
            site_for("https://other.my.salesforce.com/lightning/r/Report/00O5g00000ABCDE/view")
        assert Sandbox.DOMAIN_URL in str(error.value)  # 登録済みの組織を案内する

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
        path = tmp_path / "credentials.dat"
        save_credentials(
            {
                "sandbox_client_id": "CID",
                "sandbox_client_secret": "CSECRET",
                "sandbox_refresh_token": "RTOKEN",
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
                "comken.toolbox.salesforce.oauth_refresh.requests.post",
                return_value=_token_response(),
            ) as post,
        ):
            sf = Sandbox()

        assert isinstance(sf, Sandbox), "サブクラスのまま作られる"
        assert post.call_args.args[0] == f"{Sandbox.DOMAIN_URL}/services/oauth2/token"
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
                "comken.toolbox.salesforce.oauth_refresh.requests.post",
                return_value=_token_response(),
            ) as post,
        ):
            Sandbox(prefix="sandbox_test")

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
        monkeypatch.setattr(store, "CREDENTIALS_PATH", tmp_path / "credentials.dat")
        with pytest.raises(CredentialNotFoundError):
            Sandbox()


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

        stat = metrics.component_stats()["crud"]
        assert (stat.calls, stat.errors, stat.retries) == (1, 1, 1)
        assert metrics.retry_reason_counts() == {"再認証": 1}

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
