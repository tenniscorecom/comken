"""examples/advanced/salesforce_query/_fake_org.py — 疑似 Salesforce 組織。

SalesforceBase を継承し、HTTP 送信 (``_send``) だけを差し替える。
``bulk_query()`` / ``query()`` 本体のコードはそのまま通すため、
CSV 解析・REST のページ送り・Bulk のジョブ作成 / 状態ポーリング /
結果ページ送りの実コードが、この疑似組織を相手にそのまま動く。

認証は完全にスキップする（DPAPI を読まずに ``_access_token`` /
``_instance_url`` を直接流し込む）。Salesforce 組織・認証情報なしで
サンプルを動かすためにある。
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

import requests

from comken.toolbox.salesforce.client import SalesforceBase
from comken.toolbox.salesforce.metrics import APIMetrics
from comken.toolbox.salesforce.report import ReportAPI

logger = logging.getLogger(__name__)


# --- 疑似組織の返す固定データ ----------------------------------------------------

# bulk_query() が取る商談の 2 ページ構成 CSV。
# - Opportunity の Id 接頭辞は 006 (Account の 001 ではない)
# - 案件C の Amount は空 (null) / 案件D の Account.Name は空 (null)
# - true / false は文字列 / 参照項目 Account.Name はそのまま列名
OPPORTUNITIES_BULK_PAGE_1 = (
    "Id,Name,Account.Name,Amount,IsWon,CloseDate\n"
    "006000000000001AAA,案件A,株式会社アルファ,100000,true,2026-09-01\n"
    "006000000000001AAB,案件B,株式会社ベータ,250000,false,2026-09-15\n"
    "006000000000001AAC,案件C,株式会社アルファ,,false,2026-09-20\n"
    "006000000000001AAD,案件D,,50000,true,2026-10-01\n"
)
OPPORTUNITIES_BULK_PAGE_2 = (
    "Id,Name,Account.Name,Amount,IsWon,CloseDate\n"
    "006000000000001AAE,案件E,株式会社ガンマ,75000,true,2026-10-05\n"
)

# query() (集計) の返す dict (実 API と同じく cnt は int)。
# 上の bulk CSV 5件と件数を合わせる:
# Closed Won=3 (IsWon=true) / Prospecting=1 / Negotiation/Review=1
STAGE_AGGREGATE_RESPONSE: dict[str, Any] = {
    "records": [
        {"attributes": {"type": "AggregateResult"}, "StageName": "Prospecting", "cnt": 1},
        {"attributes": {"type": "AggregateResult"}, "StageName": "Negotiation/Review", "cnt": 1},
        {"attributes": {"type": "AggregateResult"}, "StageName": "Closed Won", "cnt": 3},
    ],
    "done": True,
}

# query() (1件取得) の返す dict (名前 → Account)。
ACCOUNT_RECORDS: dict[str, list[dict[str, Any]]] = {
    "株式会社アルファ": [
        {"attributes": {"type": "Account"}, "Id": "001000000000001XXX", "Name": "株式会社アルファ"},
    ],
    "株式会社ベータ": [
        {"attributes": {"type": "Account"}, "Id": "001000000000001YYY", "Name": "株式会社ベータ"},
    ],
}


@dataclass
class _FakeResponse:
    """``requests.Response`` の代わりに ``_send`` から返す疑似レスポンス。

    ``client.py`` が読む属性 (``status_code``・``headers``・``text``・
    ``content``・``json()``) だけ揃える。``json_body`` を渡された
    ときは ``body_text`` を JSON 文字列で初期化し、``content`` を
    非空にする（``client._body_of`` が ``not response.content`` を
    判定して None を返すのを避けるため）。
    """

    status_code: int = 200
    body_text: str = ""
    response_headers: dict[str, str] = field(default_factory=dict)
    json_body: Any = None

    def __post_init__(self) -> None:
        if self.json_body is not None and not self.body_text:
            self.body_text = json.dumps(self.json_body, ensure_ascii=False)

    @property
    def text(self) -> str:
        return self.body_text

    @property
    def content(self) -> bytes:
        return self.body_text.encode("utf-8") if self.body_text else b""

    @property
    def headers(self) -> dict[str, str]:
        return self.response_headers

    def json(self) -> Any:
        if self.json_body is not None:
            return self.json_body
        return json.loads(self.body_text)


class FakeOpportunityOrg(SalesforceBase):
    """疑似 Salesforce 組織。

    ``_send`` だけを差し替えて ``bulk_query()`` / ``query()`` の本物を生かす。

    - 認証はスキップ（DPAPI / refresh_token を読まない）
    - ``BULK_POLL_SECONDS = 0`` でジョブ状態のポーリングを即終わらせる
    - HTTP 送信 (``_send``) の戻り値で「ジョブ作成 → InProgress → JobComplete
      → 結果 CSV 2ページ（``Sforce-Locator`` 付き → ``null``）」と
      「REST query（集計と 1 件取得）」を疑似再現する
    """

    DOMAIN_URL = "https://example.my.salesforce.com"
    OWNER = "comken / examples"
    CREDENTIAL_PREFIX = ""

    BULK_POLL_SECONDS = 0  # 疑似組織は待ち時間を 0 にして即終わらせる

    JOB_ID = "JOB_FAKE_001"

    def __init__(self) -> None:
        # 親の __init__ は呼ばず、認証 (HTTP) と OWNER 検査を完全にスキップする。
        # 必要なフィールドだけ直接セットする
        self._session = requests.Session()
        self._access_token = "FAKE_ACCESS_TOKEN"
        self._instance_url = self.DOMAIN_URL.rstrip("/")
        self.metrics = APIMetrics("fake-org")
        self.report = ReportAPI(self)
        self._state_poll_count = 0

    def _authenticate(self) -> None:
        # 親の __init__ は呼ばないので本来不要。安全のため上書き。
        return

    def _send(
        self,
        method: str,
        url: str,
        body: dict[str, Any] | None,
        headers: dict[str, str] | None = None,
        data: str | None = None,
    ) -> requests.Response:  # type: ignore[override]
        """HTTP 送信の代わりに、URL で分岐して疑似組織の応答を返す。

        戻り値は ``_FakeResponse`` だが、基底クラスの戻り値型
        ``requests.Response`` と整合させるため ``# type: ignore[override]``
        を付ける（``status_code``・``headers``・``text``・``content``・
        ``json()`` を ``_FakeResponse`` が揃えるため、親側の利用は
        Duck Typing で成立する）。

        対応する URL 形状:
            - ``POST /jobs/query``                → ジョブ作成
            - ``GET  /jobs/query/{id}``           → ジョブ状態
                （1回目 InProgress、2回目 JobComplete）
            - ``GET  /jobs/query/{id}/results``   → 結果 CSV 1ページ目
                （``Sforce-Locator`` 付き）
            - ``GET  /jobs/query/{id}/results?locator=...`` → 結果 CSV 2ページ目
                （``Sforce-Locator: null`` で終了）
            - ``GET  /query?q=...``               → REST クエリ（集計・1件取得）
        """
        del body, headers, data  # 疑似組織では使わない
        # 戻り値の型は _FakeResponse だが、基底クラスと合わせて ``requests.Response`` を
        # 返す宣言にしているため、pyright にはここで警告される。``status_code`` 等を
        # 揃えているため親側の利用は Duck Typing で成立する
        return self._build_fake_response(method, url)  # type: ignore[return-value]

    def _build_fake_response(self, method: str, url: str) -> _FakeResponse:
        """URL で分岐して疑似レスポンスを組み立てる（``_send`` の本体）。"""
        parsed = urllib.parse.urlsplit(url)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        # Bulk ジョブ作成
        if method == "POST" and path.endswith("/jobs/query"):
            return _FakeResponse(
                json_body={"id": self.JOB_ID, "operation": "query", "state": "InProgress"},
                response_headers={"Content-Type": "application/json"},
            )

        # Bulk ジョブ状態（ポーリング）
        if method == "GET" and re.search(r"/jobs/query/[^/]+$", path):
            self._state_poll_count += 1
            if self._state_poll_count == 1:
                return _FakeResponse(
                    json_body={"id": self.JOB_ID, "state": "InProgress"},
                    response_headers={"Content-Type": "application/json"},
                )
            return _FakeResponse(
                json_body={"id": self.JOB_ID, "state": "JobComplete"},
                response_headers={"Content-Type": "application/json"},
            )

        # Bulk 結果 CSV（ページ送り）
        if method == "GET" and path.endswith("/results"):
            locator = qs.get("locator", [""])[0]
            if locator == "":
                # 1ページ目: Sforce-Locator 付きで次のページを示唆
                return _FakeResponse(
                    body_text=OPPORTUNITIES_BULK_PAGE_1,
                    response_headers={
                        "Content-Type": "text/csv",
                        "Sforce-Locator": "NEXT_FAKE_LOCATOR",
                    },
                )
            if locator == "NEXT_FAKE_LOCATOR":
                # 2ページ目: Sforce-Locator=null で終了
                return _FakeResponse(
                    body_text=OPPORTUNITIES_BULK_PAGE_2,
                    response_headers={"Content-Type": "text/csv", "Sforce-Locator": "null"},
                )
            # 万一それ以降のページが来ても空で返す
            return _FakeResponse(
                body_text="",
                response_headers={"Content-Type": "text/csv", "Sforce-Locator": "null"},
            )

        # REST クエリ (集計 / 1件取得)
        if method == "GET" and path.endswith("/query"):
            soql = qs.get("q", [""])[0]
            return _FakeResponse(
                json_body=self._dispatch_rest_query(soql),
                response_headers={"Content-Type": "application/json"},
            )

        # 想定外
        return _FakeResponse(
            status_code=404,
            body_text="Not Found",
            response_headers={"Content-Type": "text/plain"},
        )

    def _dispatch_rest_query(self, soql: str) -> dict[str, Any]:
        """REST クエリの SOQL に応じて疑似レスポンスを返す。

        集計クエリ (``GROUP BY`` / ``COUNT``) と 1件取得クエリ
        (``FROM Account ... LIMIT 1``) を区別する。それ以外は空を返す。
        """
        soql_upper = soql.upper()
        if "GROUP BY" in soql_upper or "COUNT(" in soql_upper:
            return STAGE_AGGREGATE_RESPONSE
        if "FROM ACCOUNT" in soql_upper and "LIMIT" in soql_upper:
            # エスケープされた ``\'`` も文字列の内側として扱う (``O'Brien`` 対策)
            match = re.search(r"Name\s*=\s*'((?:[^'\\]|\\.)*)'", soql)
            if match:
                # 実行時は Salesforce がエスケープを戻すので、こっちでも戻す
                name = match.group(1).replace("\\'", "'")
                records = ACCOUNT_RECORDS.get(name, [])
                return {"records": records, "done": True}
        return {"records": [], "done": True}
