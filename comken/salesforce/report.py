"""
salesforce/report.py — レポート API

レポート ID を渡して、明細行を [{列名: 値}, ...] で受け取る。

**同期・非同期のどちらも 2000 行が上限。** 公式ドキュメントに
"The API returns up to the first 2,000 report rows." と明記がある。
非同期にすれば超えられる、というのは誤りで、非同期の利点は
「重いレポートで HTTP タイムアウトしにくい」ことと実行枠の違いだけ。

2000 行を超えるときの対処は3段構え（docs/Salesforce.md）:

    1. 切り捨てを検知して止める  ← 既定。allow_truncated=True で警告に落とせる
    2. filters で日付などを区切り、複数回に分けて取得する
    3. それでも足りないものだけ Salesforce.query()（SOQL）へ書き換える

3 を先回りで全部やる必要はない。切り捨ては計測に残るので、
あとから「どのレポートを SOQL へ移すか」を実測で決められる。
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from ..exceptions import (
    SalesforceReportExecutionError,
    SalesforceReportFormatError,
    SalesforceReportTruncatedError,
)

if TYPE_CHECKING:  # 実行時は import しない（client と相互参照になるため）
    from .client import Salesforce

logger = logging.getLogger(__name__)

COMPONENT = "report"
ROW_LIMIT = 2000
TABULAR_FORMAT = "TABULAR"
DETAIL_ROWS_KEY = "T!T"  # 明細レポートの行が入っている factMap のキー
POLL_INTERVAL_SECONDS = 3
ASYNC_TIMEOUT_SECONDS = 120


class ReportApi:
    """レポートを実行して明細行を取得する。

    `Salesforce` が `report` 属性として持っている。単体では作らない。

        with Salesforce(...) as sf:
            rows = sf.report.run("00O000000000001")
    """

    def __init__(self, client: Salesforce) -> None:
        """
        Args:
            client: このレポート API を使う Salesforce インスタンス。
        """
        self._client = client

    def run(
        self,
        report_id: str,
        filters: list[dict] | None = None,
        allow_truncated: bool = False,
    ) -> list[dict]:
        """レポートを同期実行して明細行を返す（上限 2000 行）。

        Args:
            report_id: レポート ID（レポートを開いたときの URL の末尾。15桁 or 18桁）。
            filters: 絞り込み条件（省略可）。レポート定義の条件を実行時に上書きする。
                例: [{"column": "CREATED_DATE",
                      "operator": "greaterThan", "value": "2026-01-01"}]
            allow_truncated: True にすると、2000 行で切り捨てられても例外にせず
                警告ログだけを出して、取れた分を返す。**既定は False**
                （欠けたデータで処理が進むのを防ぐため）。

        Returns:
            [{"列の表示名": "値", ...}, ...] のリスト。

        Raises:
            SalesforceReportTruncatedError: 上限で切り捨てられた場合
                （allow_truncated=True のときは送出しない）。
            SalesforceReportFormatError: 明細（TABULAR）形式でない場合。
        """
        path = f"{self._base_path()}/{report_id}"
        if filters:
            data, _ = self._client.request(
                "POST",
                path,
                body={"reportMetadata": {"reportFilters": filters}},
                component=COMPONENT,
            )
        else:
            data, _ = self._client.request("GET", path, component=COMPONENT)
        return self._parse(data, report_id, allow_truncated)

    def run_async(
        self,
        report_id: str,
        filters: list[dict] | None = None,
        allow_truncated: bool = False,
    ) -> list[dict]:
        """レポートを非同期実行して明細行を返す（**上限は同期と同じ 2000 行**）。

        重いレポートで同期実行がタイムアウトするときに使う。
        行数の上限は緩まないので、2000 行を超えるなら filters か SOQL で対処する。

        Args:
            report_id: レポート ID。
            filters: 絞り込み条件（省略可）。
            allow_truncated: run() と同じ。

        Raises:
            SalesforceReportTruncatedError: 上限で切り捨てられた場合。
            SalesforceReportFormatError: 明細（TABULAR）形式でない場合。
            SalesforceReportExecutionError: Salesforce 側で実行が失敗した場合。
            TimeoutError: 制限時間内に完了しなかった場合。
        """
        instances_path = f"{self._base_path()}/{report_id}/instances"
        body = {"reportMetadata": {"reportFilters": filters}} if filters else {}
        started, _ = self._client.request("POST", instances_path, body=body, component=COMPONENT)
        instance_id = started["id"] if isinstance(started, dict) else ""

        deadline = time.monotonic() + ASYNC_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            data, _ = self._client.request(
                "GET", f"{instances_path}/{instance_id}", component=COMPONENT
            )
            status = data.get("status") if isinstance(data, dict) else None
            if status == "Success":
                return self._parse(data, report_id, allow_truncated)
            if status == "Error":
                detail = str(data.get("error", data.get("message", "詳細情報なし")))
                raise SalesforceReportExecutionError(report_id, detail)
            time.sleep(POLL_INTERVAL_SECONDS)

        raise TimeoutError(
            f"レポートの取得が {ASYNC_TIMEOUT_SECONDS} 秒以内に終わりませんでした: {report_id}\n"
            "レポートの対象期間を狭めるか、SOQL（query）で取得してください。"
        )

    def _base_path(self) -> str:
        return self._client.data_path("/analytics/reports")

    def _parse(self, data: object, report_id: str, allow_truncated: bool) -> list[dict]:
        """レポート API のレスポンスを [{表示名: 値}, ...] に変換する。"""
        if not isinstance(data, dict):
            return []

        metadata = data.get("reportMetadata", {})
        report_format = metadata.get("reportFormat")
        # 集計レポートは行が factMap のグループ別キーに入るため、明細用のキーを
        # そのまま読むと無言で空のリストを返してしまう。だから明示的に弾く
        if report_format and report_format != TABULAR_FORMAT:
            raise SalesforceReportFormatError(report_id, report_format)

        # allData が偽なら上限で切り捨てられている。全件と誤認させない
        if data.get("allData") is False:
            self._client.metrics.record_truncated_report(report_id)
            if not allow_truncated:
                raise SalesforceReportTruncatedError(report_id, ROW_LIMIT)
            logger.warning(
                "レポート %s は上限（%d 行）で切り捨てられました。全件ではありません。",
                report_id,
                ROW_LIMIT,
            )

        columns = metadata.get("detailColumns", [])
        column_info = data.get("reportExtendedMetadata", {}).get("detailColumnInfo", {})
        # 表示名が取れればそちらを使い、取れなければ内部名のままにする
        labels = [column_info.get(column, {}).get("label", column) for column in columns]

        rows = data.get("factMap", {}).get(DETAIL_ROWS_KEY, {}).get("rows", [])
        return [
            {label: row["dataCells"][i]["label"] for i, label in enumerate(labels)} for row in rows
        ]
