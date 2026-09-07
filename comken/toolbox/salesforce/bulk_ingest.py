"""comken/toolbox/salesforce/bulk_ingest.py — Bulk API 2.0 の Ingest ジョブ実行。

``Table``（または ``list[dict]``）の複数レコードをまとめて Salesforce へ
insert / update / upsert / delete する。``SalesforceBase`` の ``request()``
を共通経路として使い、リトライ・401 再認証・計測を共有する。

**この機能は本物の Salesforce 組織に対して未検証。** ジョブ作成・データ
アップロード・状態確認・成功/失敗結果取得のエンドポイントとレスポンス構造は
Salesforce の公式リファレンスに基づいて実装しているが、実際のレスポンスで
想定と違う点が見つかったら、このモジュールを修正すること。
"""

from __future__ import annotations

import logging
import tempfile
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from comken.core.table import Table
from comken.core.timer import measure
from comken.exceptions import (
    SalesforceBulkIngestFailedError,
    SalesforceBulkIngestTimeoutError,
)
from comken.runtime import dry_run_log, is_dry_run
from comken.toolbox.csv import CSV

if TYPE_CHECKING:  # 実行時は import しない（client と相互参照になるため）
    from comken.toolbox.salesforce.client import SalesforceBase

logger = logging.getLogger(__name__)

__all__ = ["BulkIngestAPI", "BulkIngestResult"]

COMPONENT = "bulk_ingest"
JOBS_PATH = "/jobs/ingest"
# 大量データの一括変更を想定し、レポート系（120秒）より長めの既定値にする
POLL_INTERVAL_SECONDS = 3
DEFAULT_TIMEOUT_SECONDS = 600
JOB_COMPLETE_STATE = "JobComplete"
# 本物の組織で未検証の前提: 失敗時にありえる state を列挙しておく
JOB_FAILED_STATES = ("Failed", "Aborted")
# 結果取得の ``Sforce-Locator`` ヘッダーが無い・次ページ無しのマーカー。
# 公式リファレンスでは「次ページが無いときは null 文字列」と書かれており、
# 実際の振る舞いは本物の組織で未検証。
NO_MORE_PAGES_LOCATOR = "null"


@dataclass(frozen=True)
class BulkIngestResult:
    """Bulk Ingest ジョブの実行結果。

    Attributes:
        successful: 成功した行の ``Table``（例: sf__Id, sf__Created, 元の列 ...）。
        failed: 失敗した行の ``Table``（例: sf__Id, sf__Error, 元の列 ...）。
            **1件以上の失敗行が含まれていても例外ではない**（ジョブ自体は
            正常終了しつつ一部の行が失敗することは仕様上起こり得るため、
            ここでは例外にしない。呼び出し側で ``len(result.failed)`` を
            見て判断する）。
        job_id: ジョブID。
        state: ジョブの最終状態（"JobComplete" など）。
    """

    successful: Table
    failed: Table
    job_id: str
    state: str


class BulkIngestAPI:
    """Bulk API 2.0 の Ingest ジョブで大量レコードを一括変更する。

    ``SalesforceBase`` が ``bulk_ingest`` 属性として持っている。単体では作らない。

        with Solution() as sf:
            result = sf.bulk_ingest.insert("Account", [{"Name": "テスト"}])
            if len(result.failed) > 0:
                print(f"{len(result.failed)} 行が失敗しました")

    **書き込み経路が ``DataLoaderCLI`` と異なる点:**  ``DataLoaderCLI``
    （docs/dataloader.md）はデスクトップアプリ版 Data Loader を
    サブプロセスで呼び出す方式で、デスクトップアプリのインストールが
    必要になる。``BulkIngestAPI`` は Salesforce の REST API を直接
    叩くため、**デスクトップアプリのインストールは不要**。ブラウザで
    データ変更できない環境（Data Import Wizard がない組織など）からの
    移行先として使える。

    **本物の Salesforce 組織に対して未検証。** ジョブ作成・アップロード・
    状態確認・結果取得のエンドポイントとレスポンス構造は Salesforce の
    公式リファレンスに基づいて実装しているが、実際のレスポンスで想定と
    違う点が見つかったら、このモジュールを修正すること。
    """

    def __init__(self, client: SalesforceBase) -> None:
        """
        Args:
            client: この Bulk Ingest API を使う Salesforce クライアント。
        """
        self._client = client

    @measure
    def insert(
        self,
        object_name: str,
        rows: list[dict] | Table,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> BulkIngestResult:
        """指定オブジェクトに複数レコードを一括作成する。

        ``rows`` の各 dict のキーが CSV の列名になる。Salesforce の
        項目 API 参照名（例: ``"Name"``, ``"Account__c"``）をそのまま使うこと。

        Args:
            object_name: オブジェクトの API 参照名（例: ``"Account"``）。
            rows: 作成するレコードの ``list[dict]`` または ``Table``。
            timeout_seconds: ジョブ完了を待つ上限秒数。大量データの
                投入を想定し、既定値は600秒（10分）。

        Returns:
            実行結果を表す ``BulkIngestResult``。

        Raises:
            SalesforceBulkIngestFailedError: ジョブが失敗して終わった場合
                （状態が ``Failed`` / ``Aborted``）。
            SalesforceBulkIngestTimeoutError: ``timeout_seconds`` 以内に
                ジョブが完了しなかった場合。
        """
        return self._run(object_name, "insert", rows, None, timeout_seconds)

    @measure
    def update(
        self,
        object_name: str,
        rows: list[dict] | Table,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> BulkIngestResult:
        """既存レコードを一括更新する。

        ``rows`` の各 dict には ``Id`` 列の値（Salesforce のレコード Id）を
        含めること。

        Args:
            object_name: オブジェクトの API 参照名（例: ``"Account"``）。
            rows: 更新するレコードの ``list[dict]`` または ``Table``。
                ``Id`` 列必須。
            timeout_seconds: ``insert()`` と同じ。

        Returns:
            実行結果を表す ``BulkIngestResult``。

        Raises:
            SalesforceBulkIngestFailedError: ``insert()`` から伝播。
            SalesforceBulkIngestTimeoutError: ``insert()`` から伝播。
        """
        return self._run(object_name, "update", rows, None, timeout_seconds)

    @measure
    def upsert(
        self,
        object_name: str,
        external_id_field: str,
        rows: list[dict] | Table,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> BulkIngestResult:
        """外部 ID で複数レコードを一括 upsert する（一致すれば更新、なければ作成）。

        ``rows`` の各 dict には ``external_id_field`` 列の値を含めること。

        Args:
            object_name: オブジェクトの API 参照名（例: ``"Account"``）。
            external_id_field: 外部 ID 項目の API 参照名（例: ``"ExternalId__c"``）。
            rows: upsert するレコードの ``list[dict]`` または ``Table``。
                ``external_id_field`` 列必須。
            timeout_seconds: ``insert()`` と同じ。

        Returns:
            実行結果を表す ``BulkIngestResult``。

        Raises:
            SalesforceBulkIngestFailedError: ``insert()`` から伝播。
            SalesforceBulkIngestTimeoutError: ``insert()`` から伝播。
        """
        return self._run(object_name, "upsert", rows, external_id_field, timeout_seconds)

    @measure
    def delete(
        self,
        object_name: str,
        rows: list[dict] | Table,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> BulkIngestResult:
        """既存レコードを一括削除する。

        ``rows`` の各 dict には ``Id`` 列の値（Salesforce のレコード Id）を
        含めること。``Id`` 以外の列は指定しても無視される。

        Args:
            object_name: オブジェクトの API 参照名（例: ``"Account"``）。
            rows: 削除するレコードの ``list[dict]`` または ``Table``。
                ``Id`` 列必須。
            timeout_seconds: ``insert()`` と同じ。

        Returns:
            実行結果を表す ``BulkIngestResult``。

        Raises:
            SalesforceBulkIngestFailedError: ``insert()`` から伝播。
            SalesforceBulkIngestTimeoutError: ``insert()`` から伝播。
        """
        return self._run(object_name, "delete", rows, None, timeout_seconds)

    def _run(
        self,
        object_name: str,
        operation: str,
        rows: list[dict] | Table,
        external_id_field: str | None,
        timeout_seconds: float,
    ) -> BulkIngestResult:
        """4 種類のオペレーションに共通する処理（ジョブ作成〜結果取得）をまとめる。

        ``list[dict]`` と ``Table`` を受け取り、``Table`` に揃えてから
        残りの工程へ流す。``list[dict]`` のときは 1 行目から列名を推測する
        （``SalesforceBase.query()`` と同じ流儀）。
        """
        if isinstance(rows, Table):
            table = rows
        else:
            columns = list(rows[0]) if rows else []
            table = Table(columns, list(rows))
        if is_dry_run():
            dry_run_log("Salesforce %s へ Bulk %s: %d 行", object_name, operation, len(table))
            return BulkIngestResult(
                successful=Table([], []), failed=Table([], []), job_id="", state="DRY-RUN"
            )
        csv_text = self._table_to_csv_text(table)
        job_id = self._create_job(object_name, operation, external_id_field)
        self._upload(job_id, csv_text)
        self._close_job(job_id)
        state = self._wait_until_complete(job_id, timeout_seconds)
        successful = self._fetch_result(job_id, "successfulResults")
        failed = self._fetch_result(job_id, "failedResults")
        return BulkIngestResult(successful=successful, failed=failed, job_id=job_id, state=state)

    def _create_job(
        self,
        object_name: str,
        operation: str,
        external_id_field: str | None,
    ) -> str:
        """Ingest ジョブを作成し、ジョブIDを返す（1. の POST）。

        ``upsert`` のときだけ ``externalIdFieldName`` を body に含める。
        それ以外のオペレーションで ``externalIdFieldName`` を付けると
        Salesforce 側でエラーになるため、分岐する。
        """
        path = self._client.data_path(JOBS_PATH)
        body: dict[str, str] = {
            "object": object_name,
            "operation": operation,
            "lineEnding": "LF",
            "contentType": "CSV",
        }
        if external_id_field is not None:
            body["externalIdFieldName"] = external_id_field
        logger.debug("Bulk Ingest ジョブ作成開始: %s %s", object_name, operation)
        data, _ = self._client.request("POST", path, body=body, component=COMPONENT)
        job_id = data["id"] if isinstance(data, dict) else ""
        logger.debug("Bulk Ingest ジョブ作成完了: Job ID=%s", job_id)
        return job_id

    def _upload(self, job_id: str, csv_text: str) -> None:
        """CSV 本文をアップロードする（2. の PUT）。

        ``Content-Type: text/csv`` を渡すために ``request_upload_csv()`` を
        通す。JSON ではなく生テキストを本体として送る点が ``request()`` と異なる。
        """
        path = self._client.data_path(f"{JOBS_PATH}/{job_id}/batches")
        logger.debug("Bulk Ingest データアップロード開始: Job ID=%s", job_id)
        self._client.request_upload_csv("PUT", path, csv_text, component=COMPONENT)
        logger.debug("Bulk Ingest データアップロード完了: Job ID=%s", job_id)

    def _close_job(self, job_id: str) -> None:
        """アップロード完了をジョブへ通知する（3. の PATCH）。

        ここで ``state`` を ``UploadComplete`` にしないと、Salesforce 側は
        アップロード済みとは認識せず、ジョブが走り始めない。
        """
        path = self._client.data_path(f"{JOBS_PATH}/{job_id}")
        logger.debug("Bulk Ingest ジョブを閉じる: Job ID=%s", job_id)
        self._client.request("PATCH", path, body={"state": "UploadComplete"}, component=COMPONENT)

    def _wait_until_complete(self, job_id: str, timeout_seconds: float) -> str:
        """ジョブの状態を確認し、完了（``JobComplete``）するまで待つ（4. の GET）。

        ``state`` が ``JobComplete`` になるまで ``POLL_INTERVAL_SECONDS`` 秒
        間隔で ``GET /jobs/ingest/{jobId}`` を投げる。``Failed`` / ``Aborted``
        になったら ``SalesforceBulkIngestFailedError`` を、``timeout_seconds``
        以内に ``JobComplete`` にならなければ ``SalesforceBulkIngestTimeoutError``
        を送出する。

        Returns:
            ジョブの最終状態（``"JobComplete"`` など）。
        """
        path = self._client.data_path(f"{JOBS_PATH}/{job_id}")
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            data, _ = self._client.request("GET", path, component=COMPONENT)
            state = data.get("state") if isinstance(data, dict) else None
            if state == JOB_COMPLETE_STATE:
                return state
            if state in JOB_FAILED_STATES:
                error_message = (
                    str(data.get("errorMessage", "詳細情報なし"))
                    if isinstance(data, dict)
                    else "詳細情報なし"
                )
                raise SalesforceBulkIngestFailedError(job_id, state, error_message)
            time.sleep(POLL_INTERVAL_SECONDS)
        raise SalesforceBulkIngestTimeoutError(job_id, timeout_seconds)

    def _fetch_result(self, job_id: str, result_kind: str) -> Table:
        """成功/失敗の結果 CSV を（ページングがあれば全ページ）取得して ``Table`` にする。

        ``result_kind`` は ``"successfulResults"`` または ``"failedResults"``。
        1 ページ目は ``Sforce-Locator`` ヘッダーが ``"null"`` か空なら
        最終ページ。値があれば ``?locator=<値>`` を付けて同じ結果取得 URL を
        呼ぶ。2 ページ目以降にも**ヘッダー行が含まれる**前提で、1 行目を
        捨てて連結する（本物の組織で未検証の前提）。
        """
        path = self._client.data_path(f"{JOBS_PATH}/{job_id}/{result_kind}")
        text, headers = self._client.request_csv("GET", path, component=COMPONENT)
        lines = text.splitlines()
        locator = headers.get("Sforce-Locator", "")
        while locator and locator != NO_MORE_PAGES_LOCATOR:
            next_path = f"{path}?locator={urllib.parse.quote(locator, safe='')}"
            next_text, next_headers = self._client.request_csv(
                "GET", next_path, component=COMPONENT
            )
            next_lines = next_text.splitlines()
            # 2 ページ目以降のヘッダー行を除いて連結（未検証の前提）
            lines.extend(next_lines[1:])
            locator = next_headers.get("Sforce-Locator", "")
        return self._parse_csv_text("\n".join(lines))

    @staticmethod
    def _parse_csv_text(csv_text: str) -> Table:
        """CSV 文字列を ``Table`` に変換する。

        既存の ``CSV`` クラス（ファイル読み込み）をそのまま使い回すため、
        いったん一時ファイルに書き出してから読む。0 件のときは列・行とも空の
        ``Table`` を返す。
        """
        if not csv_text.strip():
            return Table([], [])
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "bulk_ingest_result.csv"
            tmp_path.write_text(csv_text, encoding="utf-8")
            with CSV(tmp_path, read_only=True) as csv_file:
                return csv_file.read()

    @staticmethod
    def _table_to_csv_text(table: Table) -> str:
        """``Table`` を CSV テキスト（文字列）に変換する。

        ``CSV`` クラスはファイル書き込みしかしないため、いったん一時ファイル
        に書き出してから読み戻して文字列にする（``bulk_query.py`` の
        ``_parse_csv_text()`` と対称）。
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "bulk_ingest_input.csv"
            with CSV(tmp_path) as csv_file:
                csv_file.replace(table)
            return tmp_path.read_text(encoding="utf-8")
