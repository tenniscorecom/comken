r"""comken/toolbox/salesforce/report.py — レポート API

レポート ID を渡して、明細行を [{列名: 値}, ...] で受け取る。

**同期・非同期のどちらも 2000 行が上限。** 公式ドキュメントに
"The API returns up to the first 2,000 report rows." と明記がある。
非同期にすれば超えられる、というのは誤りで、非同期の利点は
「重いレポートで HTTP タイムアウトしにくい」ことと実行枠の違いだけ。

2000 行を超えるときの対処は3段構え（docs/salesforce.md）:

    1. 切り捨てを検知して止める  ← 既定。allow_truncated=True で警告に落とせる
    2. filters で日付などを区切り、複数回に分けて取得する
    3. それでも足りないものだけ SalesforceBase.query()（SOQL）へ書き換える

3 を先回りで全部やる必要はない。切り捨ては計測に残るので、
あとから「どのレポートを SOQL へ移すか」を実測で決められる。
"""

# TYPE_CHECKING 内の SalesforceBase を型注釈で使うため、注釈の評価を遅延する。
from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING

from comken.core.table import Table
from comken.core.timer import measure
from comken.exceptions import (
    SalesforceReportExecutionError,
    SalesforceReportFormatError,
    SalesforceReportIDNotFoundError,
    SalesforceReportTruncatedError,
)

# レポート ID は接頭辞 00O ＋ 英数字で、15 桁（画面）か 18 桁（API）。
# URL のどこに入っていても拾えるよう、前後は語の区切りだけを見る
REPORT_ID_PATTERN = re.compile(r"\b(00O[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?)\b")


def report_id_from_url(text: str) -> str:
    """レポートの URL からレポート ID を取り出す。ID をそのまま渡してもよい。

    管理表（レポート一覧の CSV・Excel）には**画面のアドレスをそのまま貼れる**ようにする。
    人が ID の部分だけを抜き出す工程を挟むと、そこで写し間違いが起きるため。

        https://example.my.salesforce.com/lightning/r/Report/00O5g00000ABCDEfgh/view
        → 00O5g00000ABCDEfgh

    Args:
        text: レポートの URL、またはレポート ID。前後の空白は無視する。

    Returns:
        レポート ID（15 桁または 18 桁）。

    Raises:
        SalesforceReportIDNotFoundError: レポート ID が見つからない場合。
    """
    matched = REPORT_ID_PATTERN.search(text.strip())
    if matched is None:
        raise SalesforceReportIDNotFoundError(text)
    return matched.group(1)


if TYPE_CHECKING:  # 実行時は import しない（client と相互参照になるため）
    from comken.toolbox.salesforce.client import SalesforceBase

logger = logging.getLogger(__name__)

__all__ = ["ReportAPI", "REPORT_ID_PATTERN", "report_id_from_url"]

COMPONENT = "report"
ROW_LIMIT = 2000
TABULAR_FORMAT = "TABULAR"
DETAIL_ROWS_KEY = "T!T"  # 明細レポートの行が入っている factMap のキー
POLL_INTERVAL_SECONDS = 3
ASYNC_TIMEOUT_SECONDS = 120


class ReportAPI:
    """レポートを実行して明細行を取得する。

    `SalesforceBase` が `report` 属性として持っている。単体では作らない。

        with Sandbox() as sf:
            rows = sf.report.run("00O000000000001")
    """

    def __init__(self, client: SalesforceBase) -> None:
        """
        Args:
            client: このレポート API を使う Salesforce クライアント。
        """
        self._client = client

    @measure
    def run(
        self,
        report_id: str,
        filters: list[dict] | None = None,
        allow_truncated: bool = False,
    ) -> Table:
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
            レポート明細を表す ``Table``。

        Raises:
            SalesforceReportTruncatedError: 上限で切り捨てられた場合
                （allow_truncated=True のときは送出しない）。
            SalesforceReportFormatError: 明細（TABULAR）形式でない場合。
        """
        path = f"{self._base_path()}/{report_id}"
        logger.debug("Salesforce Report取得開始: Report ID=%s", report_id)
        if filters:
            data, _ = self._client.request(
                "POST",
                path,
                body={"reportMetadata": {"reportFilters": filters}},
                component=COMPONENT,
            )
        else:
            data, _ = self._client.request("GET", path, component=COMPONENT)
        logger.debug("Salesforce APIレスポンス受信: Report ID=%s", report_id)
        labels, rows = self._parse(data, report_id, allow_truncated)
        logger.debug("Salesforce Report取得完了: Report ID=%s 件数=%d", report_id, len(rows))
        # 列は ``detailColumns`` と ``detailColumnInfo`` から組み立てた表示名を使う。
        # ``rows[0]`` からの推測だと 0 件のとき列が消えて ``table.column("列名")`` が
        # ``TableColumnNotFoundError`` で落ちる（日常の「該当0件」で壊れる）。
        return Table(labels, rows)

    @measure
    def run_async(
        self,
        report_id: str,
        filters: list[dict] | None = None,
        allow_truncated: bool = False,
    ) -> Table:
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
                labels, rows = self._parse(data, report_id, allow_truncated)
                return Table(labels, rows)
            if status == "Error":
                # data の dict への絞り込みは関数内で完結させる（再判定せず typing 用に分岐）
                if not isinstance(data, dict):
                    raise SalesforceReportExecutionError(report_id, "詳細情報なし")
                detail = str(data.get("error", data.get("message", "詳細情報なし")))
                raise SalesforceReportExecutionError(report_id, detail)
            time.sleep(POLL_INTERVAL_SECONDS)

        raise TimeoutError(
            f"レポートの取得が {ASYNC_TIMEOUT_SECONDS} 秒以内に終わりませんでした: {report_id}\n"
            "レポートの対象期間を狭めるか、SOQL（query）で取得してください。"
        )

    @measure
    def describe(self, report_id: str) -> dict:
        """レポートを実行せず、定義（列・フィルタ・形式）を取得する。

        `run()` / `run_async()` はどちらもレポートを**実行**するため 2000 行の
        上限と実行枠を消費する。`describe` は実行しないので、上限・実行枠とも
        気にせず何度でも叩ける。SOQL への移行を下書きするときの情報源として使う。

        レスポンスは API の構造をそのまま返す（`run()` のように
        `[{列名: 値}]` には畳まない）。用途が SOQL 化の下書きで、
        必要な項目がまだ定まっていないため、API の返す構造をそのまま渡して
        呼び出し側で必要な部分を取り出す方針にする。

        Args:
            report_id: レポート ID。

        Returns:
            パース済み dict。主要キーは次のとおり:

            - ``reportMetadata``: レポート定義本体
                - ``detailColumns``: 明細列（レポート用の名前。SOQL の
                  フィールドパスとは1対1ではない）
                - ``reportFilters``: フィルタ条件
                - ``reportBooleanFilter``: フィルタの論理結合
                - ``reportFormat``: ``TABULAR`` / ``SUMMARY`` / ``MATRIX`` など
            - ``reportExtendedMetadata``: 列の表示名・ラベルなど
                - ``detailColumnInfo``: 各列の表示名

            API が dict 以外を返した場合（パース失敗時など）は空 dict。

        Raises:
            SalesforceRequestError: 通信や認証に失敗した場合（`_client.request` 経由）。
        """
        path = f"{self._base_path()}/{report_id}/describe"
        logger.debug("Salesforce Report describe開始: Report ID=%s", report_id)
        data, _ = self._client.request("GET", path, component=COMPONENT)
        logger.debug("Salesforce Report describe完了: Report ID=%s", report_id)
        return data if isinstance(data, dict) else {}

    def _base_path(self) -> str:
        return self._client.data_path("/analytics/reports")

    def _parse(
        self, data: object, report_id: str, allow_truncated: bool
    ) -> tuple[list[str], list[dict]]:
        """レポート API のレスポンスを ``(表示名の列リスト, [{表示名: 値}, ...])`` に変換する。

        0 件のときでも ``detailColumns`` / ``detailColumnInfo`` から組み立てた
        ``labels`` を返すため、``Table`` の列情報が落ちない。
        """
        if not isinstance(data, dict):
            return [], []

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
        return labels, [
            {label: row["dataCells"][i]["label"] for i, label in enumerate(labels)} for row in rows
        ]
