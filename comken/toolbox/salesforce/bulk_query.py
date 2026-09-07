"""comken/toolbox/salesforce/bulk_query.py — Bulk API 2.0 の Query ジョブ実行。

SOQL を非同期ジョブとして Salesforce に投げ、完了後に結果 CSV を ``Table``
に詰めて返す。

**SalesforceBase.query()**（同期 SOQL・ページング対応済み）でも全件は
取得できるが、クエリが重く同期の実行時間制約に当たる場合はこちらを使う。
Bulk API はジョブを作って完了を待つ非同期方式のため、重いクエリでも
タイムアウトしにくい。

**書き込み系（Ingest）は対象外。** 大量データの書き込みは既存の
``DataLoaderCLI``（docs/dataloader.md）に任せる。

**本物の Salesforce 組織に対して未検証。** ジョブ作成・状態確認・結果取得の
エンドポイントとレスポンス構造は Salesforce の公式リファレンスに基づいて
実装しているが、実際のレスポンスで想定と違う点が見つかったら、この
モジュールを修正すること。
"""

from __future__ import annotations

import logging
import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import TYPE_CHECKING

from comken.core.table import Table
from comken.core.timer import measure
from comken.exceptions import (
    SalesforceBulkQueryFailedError,
    SalesforceBulkQueryTimeoutError,
)
from comken.toolbox.csv import CSV

if TYPE_CHECKING:  # 実行時は import しない（client と相互参照になるため）
    from comken.toolbox.salesforce.client import SalesforceBase

logger = logging.getLogger(__name__)

__all__ = ["BulkQueryAPI"]

COMPONENT = "bulk_query"
JOBS_PATH = "/jobs/query"
# 大量データの抽出を想定し、レポート系（120秒）より長めの既定値にする
POLL_INTERVAL_SECONDS = 3
DEFAULT_TIMEOUT_SECONDS = 600
JOB_COMPLETE_STATE = "JobComplete"
# 本物の組織で未検証の前提: 失敗時にありえる state を列挙しておく
JOB_FAILED_STATES = ("Failed", "Aborted")
# 結果取得の ``Sforce-Locator`` ヘッダーが無い・次ページ無しのマーカー。
# 公式リファレンスでは「次ページが無いときは null 文字列」と書かれており、
# 実際の振る舞いは本物の組織で未検証。
NO_MORE_PAGES_LOCATOR = "null"


class BulkQueryAPI:
    """Bulk API 2.0 の Query ジョブで SOQL を非同期実行する。

    ``SalesforceBase`` が ``bulk_query`` 属性として持っている。単体では作らない。

        with Solution() as sf:
            table = sf.bulk_query.run("SELECT Id, Name FROM Account")

    ``SalesforceBase.query()``（同期 SOQL・ページング対応済み）でも全件は
    取得できるが、クエリが重く同期の実行時間制約に当たる場合はこちらを使う。
    Bulk API はジョブを作って完了を待つ非同期方式のため、重いクエリでも
    タイムアウトしにくい。

    **本物の Salesforce 組織に対して未検証。** ジョブ作成・状態確認・結果取得の
    エンドポイントとレスポンス構造は Salesforce の公式リファレンスに基づいて
    実装しているが、実際のレスポンスで想定と違う点が見つかったら、この
    モジュールを修正すること。
    """

    def __init__(self, client: SalesforceBase) -> None:
        """
        Args:
            client: この Bulk Query API を使う Salesforce クライアント。
        """
        self._client = client

    @measure
    def run(self, soql: str, *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> Table:
        """SOQL を Bulk API 2.0 の Query ジョブとして実行し、結果を ``Table`` で返す。

        ジョブを作成し、完了（またはタイムアウト・失敗）まで待ってから、
        結果 CSV を（ページングがあれば全ページ）取得して ``Table`` に変換する。

        Args:
            soql: 実行する SOQL クエリ文字列。
            timeout_seconds: ジョブ完了を待つ上限秒数。大量データの抽出を
                想定し、既定値は600秒（10分）。

        Returns:
            クエリ結果を表す ``Table``。0件のときは列・行とも空。

        Raises:
            SalesforceBulkQueryFailedError: ジョブが失敗して終わった場合
                （状態が Failed / Aborted）。
            SalesforceBulkQueryTimeoutError: timeout_seconds 以内にジョブが
                完了しなかった場合。
        """
        job_id = self._create_job(soql)
        self._wait_until_complete(job_id, timeout_seconds)
        csv_text = self._fetch_all_results(job_id)
        return self._parse_csv_text(csv_text)

    @measure
    def run_csv(
        self, soql: str, path: str | Path, *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    ) -> Path:
        """``run()`` の結果をそのまま CSV へ保存する。

        ``run()`` が返す ``Table`` を ``CSV`` へ書き出すだけの薄い層
        （``ReportAPI.run_csv()`` と同じ形）。

        Args:
            soql: 実行する SOQL クエリ文字列。
            path: 保存先の CSV パス（拡張子は ``.csv``）。
            timeout_seconds: ``run()`` と同じ。

        Returns:
            保存した CSV のパス。

        Raises:
            SalesforceBulkQueryFailedError: ``run()`` から伝播。
            SalesforceBulkQueryTimeoutError: ``run()`` から伝播。
        """
        table = self.run(soql, timeout_seconds=timeout_seconds)
        csv_path = Path(path)
        with CSV(csv_path) as csv_file:
            csv_file.replace(table)
        return csv_path

    def _create_job(self, soql: str) -> str:
        """クエリジョブを作成し、ジョブIDを返す。"""
        path = self._client.data_path(JOBS_PATH)
        logger.debug("Bulk Query ジョブ作成開始")
        data, _ = self._client.request(
            "POST", path, body={"operation": "query", "query": soql}, component=COMPONENT
        )
        job_id = data["id"] if isinstance(data, dict) else ""
        logger.debug("Bulk Query ジョブ作成完了: Job ID=%s", job_id)
        return job_id

    def _wait_until_complete(self, job_id: str, timeout_seconds: float) -> None:
        """ジョブの状態を確認し、完了するまで待つ。

        ``state`` が ``JobComplete`` になるまで ``POLL_INTERVAL_SECONDS`` 秒
        間隔で ``GET /jobs/query/{jobId}`` を投げる。``Failed`` / ``Aborted``
        になったら ``SalesforceBulkQueryFailedError`` を、``timeout_seconds``
        以内に ``JobComplete`` にならなければ ``SalesforceBulkQueryTimeoutError``
        を送出する。
        """
        path = self._client.data_path(f"{JOBS_PATH}/{job_id}")
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            data, _ = self._client.request("GET", path, component=COMPONENT)
            state = data.get("state") if isinstance(data, dict) else None
            if state == JOB_COMPLETE_STATE:
                return
            if state in JOB_FAILED_STATES:
                error_message = (
                    str(data.get("errorMessage", "詳細情報なし"))
                    if isinstance(data, dict)
                    else "詳細情報なし"
                )
                raise SalesforceBulkQueryFailedError(job_id, state, error_message)
            time.sleep(POLL_INTERVAL_SECONDS)
        raise SalesforceBulkQueryTimeoutError(job_id, timeout_seconds)

    def _fetch_all_results(self, job_id: str) -> str:
        """結果 CSV を（ページングがあれば全ページ）取得し、1つの文字列に連結する。

        1ページ目は ``Sforce-Locator`` ヘッダーが ``"null"`` か空なら
        最終ページ。値があれば ``?locator=<値>`` を付けて同じ結果取得 URL を
        呼ぶ。2ページ目以降にも**ヘッダー行が含まれる**前提で、1行目を捨てて
        連結する（本物の組織で未検証の前提）。
        """
        path = self._client.data_path(f"{JOBS_PATH}/{job_id}/results")
        text, headers = self._client.request_csv("GET", path, component=COMPONENT)
        lines = text.splitlines()
        locator = headers.get("Sforce-Locator", "")
        while locator and locator != NO_MORE_PAGES_LOCATOR:
            next_path = f"{path}?locator={urllib.parse.quote(locator, safe='')}"
            next_text, next_headers = self._client.request_csv(
                "GET", next_path, component=COMPONENT
            )
            next_lines = next_text.splitlines()
            # 2ページ目以降のヘッダー行を除いて連結（未検証の前提）
            lines.extend(next_lines[1:])
            locator = next_headers.get("Sforce-Locator", "")
        return "\n".join(lines)

    @staticmethod
    def _parse_csv_text(csv_text: str) -> Table:
        """CSV 文字列を ``Table`` に変換する。

        既存の ``CSV`` クラス（ファイル読み込み）をそのまま使い回すため、
        いったん一時ファイルに書き出してから読む。0件のときは列・行とも空の
        ``Table`` を返す。
        """
        if not csv_text.strip():
            return Table([], [])
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "bulk_query_result.csv"
            tmp_path.write_text(csv_text, encoding="utf-8")
            with CSV(tmp_path, read_only=True) as csv_file:
                return csv_file.read()
