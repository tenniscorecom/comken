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
from pathlib import Path
from typing import TYPE_CHECKING, Any

from comken.core.table import Table
from comken.core.timer import measure
from comken.exceptions import (
    SalesforceReportAccessDeniedError,
    SalesforceReportExecutionError,
    SalesforceReportFormatError,
    SalesforceReportIDNotFoundError,
    SalesforceReportTruncatedError,
    SalesforceRequestError,
)
from comken.toolbox.csv import CSV

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


def _parse_report_payload(
    data: object,
    report_id: str,
    allow_truncated: bool,
    *,
    metrics: Any | None = None,
) -> Table:
    """レポート API のレスポンスを ``Table``（表示名の列 + {表示名: 値} の行）に変換する。

    0 件のときでも ``detailColumns`` / ``detailColumnInfo`` から組み立てた
    列を ``Table`` に持たせるため、列情報が落ちない。

    ``metrics`` は切り捨てを計測するためのフック（``APIMetrics.record_truncated_report``
    互換のメソッド ``record_truncated_report(report_id)`` を持つオブジェクト）。
    通常は ``SalesforceBase.metrics`` を渡す。テストや単発呼び出しで None の
    ときは計測をスキップする。

    Returns:
        表示名の列と行 dict を持つ ``Table``。
    """
    if not isinstance(data, dict):
        return Table([], [])

    metadata = data.get("reportMetadata", {})
    report_format = metadata.get("reportFormat")
    # 集計レポートは行が factMap のグループ別キーに入るため、明細用のキーを
    # そのまま読むと無言で空のリストを返してしまう。だから明示的に弾く
    if report_format and report_format != TABULAR_FORMAT:
        raise SalesforceReportFormatError(report_id, report_format)

    # allData が偽なら上限で切り捨てられている。全件と誤認させない
    if data.get("allData") is False:
        if metrics is not None:
            metrics.record_truncated_report(report_id)
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
    return Table(
        labels,
        [{label: row["dataCells"][i]["label"] for i, label in enumerate(labels)} for row in rows],
    )


def _normalize_label(label: str) -> str:
    """表示名の前後空白を落として小文字化する。

    Salesforce の表示名は前後に空白が入ることがあり、また大小文字の
    ゆらぎ（カスタム表示名）は実フィールド側と一致しないことがあるため、
    突き合わせの前にもう一段正規化する。完全一致しなかったときの
    フォールバック（部分一致など）は敢えて行わない。**不一致は「不一致」**
    のまま残し、誤った候補を押し付けないことを優先するため。
    """
    return label.strip().lower()


def _build_field_index(data: object) -> tuple[dict[str, list[dict]], None]:
    """Object Describe の ``fields`` 配列を ``{正規化表示名: [field, ...]}`` に組み立てる。

    同じ表示名を持つフィールドが複数ある場合は、最初に見つかった1件だけを
    選ばず**リストのまま**残す。呼び出し側で件数を判定し、1 件なら採用、
    2 件以上なら「複数候補あり」として注記する。

    Object Describe が ``fields`` を返さなかった場合（壊れたレスポンス等）は
    空の辞書を返し、全列が「対応フィールドなし」になる。例外にはしない
    （``describe_fields()`` のポリシーと揃えるため）。
    """
    fields = data.get("fields", []) if isinstance(data, dict) else []
    index: dict[str, list[dict]] = {}
    for field in fields:
        if not isinstance(field, dict):
            continue
        name = field.get("name")
        label = field.get("label")
        field_type = field.get("type")
        if not isinstance(name, str) or not isinstance(label, str):
            continue
        index.setdefault(_normalize_label(label), []).append(
            {"name": name, "type": field_type if isinstance(field_type, str) else ""}
        )
    return index, None


class ReportAPI:
    """レポートを実行して明細行を取得する。

    `SalesforceBase` が `report` 属性として持っている。単体では作らない。

        with Sandbox() as sf:
            rows = sf.report.get("00O000000000001")
    """

    def __init__(self, client: SalesforceBase) -> None:
        """
        Args:
            client: このレポート API を使う Salesforce クライアント。
        """
        self._client = client

    def _request(
        self,
        report_id: str,
        method: str,
        path: str,
        body: dict | None = None,
    ) -> tuple[dict | list | str | None, dict]:
        """``self._client.request()`` を呼び、401 / 403 だけレポート専用の
        分かりやすいエラーに差し替える。それ以外のステータスは元の例外のまま。

        Salesforce は Reports and Dashboards REST API を「Analytics API」と呼ぶことが
        あり、CRM Analytics（旧 Einstein Analytics）と紛らわしい。メッセージの文言では
        判定せず、HTTP ステータスコード（401 / 403）という確実な情報だけで判定する。
        """
        try:
            return self._client.request(method, path, body=body, component=COMPONENT)
        except SalesforceRequestError as exc:
            if exc.status_code in (401, 403):
                raise SalesforceReportAccessDeniedError(
                    report_id, exc.status_code, exc.detail
                ) from exc
            raise

    @measure
    def get(
        self,
        report_id: str,
        filters: list[dict] | None = None,
        allow_truncated: bool = False,
    ) -> Table:
        """レポートを同期実行して明細行を ``Table`` で返す（上限 2000 行）。

        列は HTTP レスポンスの ``detailColumns`` から組み立てた表示名を使い、
        **0 件のときも列情報が落ちない**（``detailColumns`` が ``["取引先名", "金額"]``
        なら、0 件ヒットでも ``Table.columns == ["取引先名", "金額"]``）。

        Args:
            report_id: レポート ID（レポートを開いたときの URL の末尾。15桁 or 18桁）。
            filters: 絞り込み条件（省略可）。
            allow_truncated: True にすると、2000 行で切り捨てられても例外にせず
                警告ログだけを出して、取れた分を返す。**既定は False**
                （欠けたデータで処理が進むのを防ぐため）。

        Returns:
            レポート明細を表す ``Table``。

        Raises:
            SalesforceReportTruncatedError: 上限で切り捨てられた場合
                （allow_truncated=True のときは送出しない）。
            SalesforceReportFormatError: 明細（TABULAR）形式でない場合。
            SalesforceReportAccessDeniedError: レポート API への権限が無い場合
                （HTTP 401 / 403）。
        """
        return self._fetch_report_table(report_id, filters, allow_truncated)

    @measure
    def run_csv(
        self,
        report_id: str,
        path: str | Path,
        filters: list[dict] | None = None,
        allow_truncated: bool = False,
    ) -> Path:
        """レポートを同期実行して、結果をそのまま CSV へ保存する。

        ``get()`` が返す ``Table`` を ``CSV`` へ書き出すだけの薄い層。
        ``Table`` 自体はファイル I/O を持たない設計（保存先の責任を分ける）ため、
        レポートを直接 CSV で欲しいだけのときはこちらを使う。

        Args:
            report_id: レポート ID（レポートを開いたときの URL の末尾。15桁 or 18桁）。
            path: 保存先の CSV パス（拡張子は ``.csv``）。
            filters: 絞り込み条件（省略可）。
            allow_truncated: ``get()`` と同じ。

        Returns:
            保存した CSV のパス。

        Raises:
            SalesforceReportTruncatedError: 上限で切り捨てられた場合
                （``get()`` から伝播）。
            SalesforceReportFormatError: 明細（TABULAR）形式でない場合
                （``get()`` から伝播）。
            SalesforceReportAccessDeniedError: レポート API への権限が無い場合
                （HTTP 401 / 403、``get()`` から伝播）。
        """
        table = self.get(report_id, filters, allow_truncated)
        csv_path = Path(path)
        with CSV(csv_path) as csv_file:
            csv_file.replace(table)
        return csv_path

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
            allow_truncated: get() と同じ。

        Raises:
            SalesforceReportTruncatedError: 上限で切り捨てられた場合。
            SalesforceReportFormatError: 明細（TABULAR）形式でない場合。
            SalesforceReportExecutionError: Salesforce 側で実行が失敗した場合。
            SalesforceReportAccessDeniedError: レポート API への権限が無い場合
                （HTTP 401 / 403）。
            TimeoutError: 制限時間内に完了しなかった場合。
        """
        instances_path = f"{self._base_path()}/{report_id}/instances"
        body = {"reportMetadata": {"reportFilters": filters}} if filters else {}
        started, _ = self._request(report_id, "POST", instances_path, body=body)
        instance_id = started["id"] if isinstance(started, dict) else ""

        deadline = time.monotonic() + ASYNC_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            data, _ = self._request(report_id, "GET", f"{instances_path}/{instance_id}")
            status = data.get("status") if isinstance(data, dict) else None
            if status == "Success":
                return _parse_report_payload(
                    data, report_id, allow_truncated, metrics=self._client.metrics
                )
            if status == "Error":
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

        `get()` / `run_async()` はどちらもレポートを**実行**するため 2000 行の
        上限と実行枠を消費する。`describe` は実行しないので、上限・実行枠とも
        気にせず何度でも叩ける。SOQL への移行を下書きするときの情報源として使う。

        レスポンスは API の構造をそのまま返す（`get()` のように
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
            SalesforceReportAccessDeniedError: レポート API への権限が無い場合
                （HTTP 401 / 403）。HTTP 401 / 403 以外は ``SalesforceRequestError``
                のまま送出される（``_request`` 経由で 401 / 403 だけ変換するため）。
        """
        path = f"{self._base_path()}/{report_id}/describe"
        logger.debug("Salesforce Report describe開始: Report ID=%s", report_id)
        data, _ = self._request(report_id, "GET", path)
        logger.debug("Salesforce Report describe完了: Report ID=%s", report_id)
        return data if isinstance(data, dict) else {}

    def _base_path(self) -> str:
        return self._client.data_path("/analytics/reports")

    def _fetch_report_table(
        self,
        report_id: str,
        filters: list[dict] | None,
        allow_truncated: bool,
    ) -> Table:
        """HTTP 取得とパースを行い ``Table`` を返す。"""
        path = f"{self._base_path()}/{report_id}"
        logger.debug("Salesforce Report取得開始: Report ID=%s", report_id)
        if filters:
            data, _ = self._request(
                report_id,
                "POST",
                path,
                body={"reportMetadata": {"reportFilters": filters}},
            )
        else:
            data, _ = self._request(report_id, "GET", path)
        logger.debug("Salesforce APIレスポンス受信: Report ID=%s", report_id)
        table = _parse_report_payload(
            data, report_id, allow_truncated, metrics=self._client.metrics
        )
        logger.debug("Salesforce Report取得完了: Report ID=%s 件数=%d", report_id, len(table))
        return table

    @measure
    def describe_fields(self, report_id: str) -> Table:
        """レポートの列と、Salesforce の実フィールド API 名の対応表を作る。

        **完全な自動変換ではない点に注意。** Salesforce の Reports API は、
        レポートの列と実フィールドの対応を保証する公式な手段を提供していない。
        そのため本メソッドは、レポートの**表示名**と主オブジェクト（標準
        レポートタイプなら ``Opportunity`` など）の**フィールドの表示名**を
        突き合わせて、同じ表示名なら実フィールドの API 名・型を埋める実装に
        とどめている。一致しない列は黙って外さず「対応フィールドなし」として
        残し、同じ表示名のフィールドが複数ある列は誤った候補を押し付けない
        ように「複数候補あり」と注記する。「9割自動で埋めて、残りをはっきり
        見せる」道具として使う。

        利用例（何十件ものレポートをまとめて CSV へ落とす）:

            with Sandbox() as sf:
                for report_id in report_ids:
                    sf.report.describe_fields_csv(report_id, f"fields_{report_id}.csv")

        Args:
            report_id: レポート ID。

        Returns:
            ``Table``。列は次のとおり（すべて日本語）:

            - ``列キー``: レポート側の列キー（``detailColumns`` の値そのもの）
            - ``表示名``: レポート API が返した表示名
            - ``対応フィールドAPI名``: 一致した実フィールドの API 名。分からなければ
              ``"(不明)"`` を入れる（空文字だと「調べたが空」と「調べていない」が
              区別できないため）
            - ``型``: 実フィールドのデータ型
            - ``備考``: 複数候補あり・オブジェクト特定失敗などの理由。1 件で
              一致した行は空文字
        """
        metadata = self.describe(report_id)
        columns = (
            metadata.get("reportMetadata", {}).get("detailColumns", [])
            if isinstance(metadata, dict)
            else []
        )
        column_info = (
            metadata.get("reportExtendedMetadata", {}).get("detailColumnInfo", {})
            if isinstance(metadata, dict)
            else {}
        )
        object_name = (
            metadata.get("reportMetadata", {}).get("reportType", {}).get("type", "")
            if isinstance(metadata, dict)
            else ""
        )

        # Object Describe 自体は /analytics/ ではないため、self._request() を
        # 通すと 401/403 が SalesforceReportAccessDeniedError に変換されてしまう。
        # ここは別系統の権限（オブジェクトへの参照）なので、変換せず
        # SalesforceRequestError のまま伝播させる。
        field_index: dict[str, list[dict]] | None
        object_error_reason: str | None
        if not object_name:
            field_index = None
            object_error_reason = (
                "レポートタイプから主オブジェクトを特定できないため自動判定できません。"
                "手動で確認してください"
            )
        else:
            path = self._client.data_path(f"/sobjects/{object_name}/describe")
            try:
                data, _ = self._client.request("GET", path, component=COMPONENT)
            except SalesforceRequestError as exc:
                # 401 / 403 は権限エラー。Reports API とは別の権限系統
                # （オブジェクトへの参照）なので、SalesforceReportAccessDeniedError には
                # 変換せず SalesforceRequestError のまま呼び出し側へ返す。
                if exc.status_code in (401, 403):
                    raise
                # 404 等は「複合レポートタイプなどで主オブジェクト名が見つからない」等
                # の想定ケース。例外にせず、全列を「(不明)」で返して道具として動く状態を保つ。
                field_index = None
                object_error_reason = (
                    f"主オブジェクト {object_name} の Object Describe に失敗したため"
                    f"自動判定できません（HTTP {exc.status_code}: {exc.detail}）。"
                    "手動で確認してください"
                )
            else:
                field_index, object_error_reason = _build_field_index(data)

        rows: list[dict[str, str]] = []
        for column_key in columns:
            info = column_info.get(column_key, {}) if isinstance(column_info, dict) else {}
            label = info.get("label", column_key) if isinstance(info, dict) else column_key
            row = {
                "列キー": column_key,
                "表示名": label,
                "対応フィールドAPI名": "(不明)",
                "型": "",
                "備考": "",
            }
            if field_index is None or object_error_reason is not None:
                # オブジェクト特定失敗 / Object Describe 失敗の全列共通
                row["備考"] = object_error_reason or ""
            else:
                matches = field_index.get(_normalize_label(label), [])
                if len(matches) == 1:
                    field = matches[0]
                    row["対応フィールドAPI名"] = field["name"]
                    row["型"] = field["type"]
                elif len(matches) > 1:
                    candidates = ", ".join(f"{field['name']}({field['type']})" for field in matches)
                    row["備考"] = f"複数候補あり: {candidates}"
                else:
                    row["備考"] = "対応フィールドなし"
            rows.append(row)
        return Table(
            ["列キー", "表示名", "対応フィールドAPI名", "型", "備考"],
            rows,
        )

    @measure
    def describe_fields_csv(self, report_id: str, path: str | Path) -> Path:
        """``describe_fields()`` の結果を CSV へ保存する。

        ``run_csv()`` が ``get()`` の結果を CSV へ保存する薄い層なのと
        同じ形。``Table`` 自体はファイル I/O を持たない設計のため、
        レポートの列-フィールド対応表を直接 CSV で欲しいときはこちらを使う。

        Args:
            report_id: レポート ID。
            path: 保存先の CSV パス（拡張子は ``.csv``）。

        Returns:
            保存した CSV のパス。
        """
        table = self.describe_fields(report_id)
        csv_path = Path(path)
        with CSV(csv_path) as csv_file:
            csv_file.replace(table)
        return csv_path
