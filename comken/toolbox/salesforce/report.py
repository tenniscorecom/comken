r"""comken/toolbox/salesforce/report.py — レポート API

レポート ID を渡して、明細行を [{列名: 値}, ...] で受け取る。

**同期・非同期のどちらも 2000 行が上限。** 公式ドキュメントに
"The API returns up to the first 2,000 report rows." と明記がある。
非同期にすれば超えられる、というのは誤りで、非同期の利点は
「重いレポートで HTTP タイムアウトしにくい」ことと実行枠の違いだけ。

2000 行を超えるときの対処は3段構え（docs/機能/salesforce.md）:

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
from itertools import zip_longest
from pathlib import Path
from typing import TYPE_CHECKING, Any

from comken.core.table import Table
from comken.core.timer import measure
from comken.exceptions import (
    SalesforceError,
    SalesforceReportIDNotFoundError,
    SalesforceReportTruncatedError,
    SalesforceRequestError,
)
from comken.toolbox.csv import CSV


def _report_format_error(report_id: str, report_format: str) -> SalesforceError:
    """``SalesforceError`` の「レポートの形式が対応していない」文言。

    取得対象は明細（TABULAR）・サマリー（SUMMARY）・マトリックス（MATRIX）の
    3 形式に限り、それ以外（MULTI_BLOCK など）は対応しないので明示的に止める。
    「明細の列が無いサマリー」のような、形式は対応内だが中身が取れない
    ケースでも使う（呼び出し側で ``report_format`` に短い理由を渡す）。
    """
    return SalesforceError(
        f"このレポートは {report_format} 形式です: {report_id}\n"
        "取得できるのは明細（TABULAR）・サマリー（SUMMARY）・"
        "マトリックス（MATRIX）形式のレポートだけです。\n"
        "レポート形式を確認するか、SOQL（query）で取得してください。"
        "\n対処: レポート形式を確認するか、管理者へ連絡してください。"
    )


def _report_access_denied_error(report_id: str, status_code: int, detail: str) -> SalesforceError:
    """``SalesforceError`` の「レポート API へのアクセスを拒否された」文言。"""
    return SalesforceError(
        f"Salesforce のレポート API（Analytics API）へのアクセスが"
        f"拒否されました（HTTP {status_code}）: {report_id}\n"
        f"{detail}\n"
        "Salesforce 管理者に、実行ユーザーの「API Enabled」権限・"
        "レポートへのアクセス権・組織の Edition が Reports and Dashboards "
        "REST API に対応しているかを確認してもらってください。"
        "\n対処: Salesforce 管理者に、refresh_token を発行したユーザーについて"
        "次を確認してもらってください。"
        "  1. Profile / Permission Set に「API Enabled」権限があるか"
        "  2. 対象のレポート・レポートフォルダへのアクセス権があるか"
        "  3. 組織の Edition・ライセンスが Reports and Dashboards REST API"
        "に対応しているか（一部の制限ライセンスでは使えない）"
    )


def _report_execution_error(report_id: str, detail: str) -> SalesforceError:
    """``SalesforceError`` の「Salesforce 側でレポート実行に失敗した」文言。"""
    return SalesforceError(
        f"Salesforce のレポート実行に失敗しました: {report_id}\n"
        f"{detail}\n"
        "Salesforce でレポートを直接実行し、条件・権限・参照項目を確認してください。"
        "\n対処: Salesforce で同じレポートを直接実行し、表示された内容を管理者へ連絡してください。"
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
SUMMARY_FORMAT = "SUMMARY"
MATRIX_FORMAT = "MATRIX"
SUPPORTED_REPORT_FORMATS = frozenset({TABULAR_FORMAT, SUMMARY_FORMAT, MATRIX_FORMAT})
DETAIL_ROWS_KEY = "T!T"  # 明細レポートの行が入っている factMap のキー
INCLUDE_DETAILS_QUERY = "includeDetails=true"
INCLUDE_DETAILS_BODY = "includeDetails"
POLL_INTERVAL_SECONDS = 3
ASYNC_TIMEOUT_SECONDS = 120


def _with_include_details_query(path: str) -> str:
    """パスに ``includeDetails=true`` のクエリを足す（GET で使う）。"""
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}{INCLUDE_DETAILS_QUERY}"


def _with_include_details_body(body: dict[str, Any] | None) -> dict[str, Any]:
    """body に ``includeDetails`` の指定を足す（POST で使う）。"""
    merged: dict[str, Any] = dict(body or {})
    merged[INCLUDE_DETAILS_BODY] = True
    return merged


def _walk_groupings(
    groupings: list[dict[str, Any]],
) -> Any:
    """``groupingsDown.groupings`` / ``groupingsAcross.groupings`` を深さ優先で歩き、
    各リーフ（``groupings`` が空配列）に対して ``(key_tuple, label_tuple)`` を yield する。

    ``key_tuple`` は **リーフ自体の ``group["key"]`` のタプル**で、親キーを連結した
    形は含まない（``factMap`` のキーを ``"_".join(key_tuple)`` で組み立てるため、
    リーフの ``key`` が ``"0_0"`` ならそのまま ``"0_0!T"`` になる必要がある）。
    ``label_tuple`` はルートからリーフまでの ``group["label"]`` を連結する
    （複数段 SUMMARY の各段の列に値を入れるため）。

    ``groupings`` が空（グループ 0 段）のときは ``([], [])`` を 1 回だけ yield する
    （``T!T`` の ``factMap`` キーに対応する想定）。
    """
    if not groupings:
        yield [], []
        return
    for group in groupings:
        key = group.get("key", "")
        label = group.get("label", "")
        sub_groupings = group.get("groupings", []) or []
        if sub_groupings:
            for inner_keys, inner_labels in _walk_groupings(sub_groupings):
                # 内側のキーはリーフのキーをそのまま使い、ラベルだけ親分を追加する
                yield inner_keys, (label, *inner_labels)
        else:
            yield (key,), (label,)


def _max_grouping_depth(groupings: list[dict[str, Any]]) -> int:
    """``groupingsDown.groupings`` / ``groupingsAcross.groupings`` のツリー全体の
    最大深さを返す。空のときは 0。

    各段とも「グループ列 1 つ」を表すとみなして段数を数える（枝分かれしている
    部分は代表深さに影響しない）。
    """
    if not groupings:
        return 0

    max_depth = 0

    def depth_of(node: dict[str, Any], current: int) -> None:
        """``node`` から下をたどって最深の深さを ``max_depth`` に反映する。"""
        nonlocal max_depth
        if current > max_depth:
            max_depth = current
        for child in node.get("groupings", []) or []:
            depth_of(child, current + 1)

    for node in groupings:
        depth_of(node, 1)
    return max_depth


def _first_node_at_depth(root: dict[str, Any], target_depth: int) -> dict[str, Any] | None:
    """ルート要素 ``root`` から見て、深さ ``target_depth``（1 始まり）に
    ある最初の要素を DFS で返す。見つからなければ ``None`` を返す。

    ルートの深さは 1 とし、深さ ``target_depth`` の要素が無い枝は探索しない。
    """
    if target_depth < 1:
        return None

    def walk(node: dict[str, Any], current: int) -> dict[str, Any] | None:
        """``node`` から下を DFS し、``current`` が ``target_depth`` の要素を返す。"""
        if current == target_depth:
            return node
        for child in node.get("groupings", []) or []:
            found = walk(child, current + 1)
            if found is not None:
                return found
        return None

    return walk(root, 1)


def _grouping_column_definitions(
    grouping_info: dict[str, Any], groupings: list[dict[str, Any]]
) -> list[tuple[str, str]]:
    """``groupingsDown.groupings`` / ``groupingsAcross.groupings`` の列メタを
    段ごとに取り、 ``(name, label)`` を段の浅い順に並べて返す。

    各段の代表（その深さで最初に出てくる要素）の ``name`` を ``groupingColumnInfo``
    のキーとして使う。``name`` が空や重複に当たったらそこで打ち切る
    （「この段に対応する name は無い」という意味）。
    表示名は ``reportExtendedMetadata.groupingColumnInfo[name].label``、取れなければ
    内部名そのまま。

    ツリー全体の最大深さを段数として、段ごとに 1 つずつ name を取りに行くので、
    ルートしか持たない 1 段 SUMMARY でも、深い入れ子でも同じ手順で列が決まる。

    ``grouping_info`` は呼び出し側で ``reportExtendedMetadata.groupingColumnInfo``
    を渡したもの（``{name: {"label": ...}}`` の dict）。
    """
    if not groupings:
        return []

    column_info = grouping_info or {}
    max_depth = _max_grouping_depth(groupings)
    names: list[str] = []
    seen: set[str] = set()
    for depth in range(1, max_depth + 1):
        node = _first_node_at_depth(groupings[0], depth)
        if node is None:
            break
        name = node.get("name", "")
        if not name or name in seen:
            break
        seen.add(name)
        names.append(name)

    return [(name, column_info.get(name, {}).get("label", name)) for name in names]


def _factmap_key(row_keys: tuple[str, ...], col_keys: tuple[str, ...] | None) -> str:
    """行グループ・列グループの最深キーから、``factMap`` のキーを組み立てる。

    行だけ（SUMMARY）のときは ``row_part!T``、両方（MATRIX）のときは ``row_part!col_part``。
    各パートが空（グループ 0 段）のときは ``"T"`` を代わりに入れる（SUMMARY の 0 段では
    ``T!T``、MATRIX の片側 0 段では ``T!T`` などがある）。
    """
    row_part = "_".join(row_keys) if row_keys else "T"
    if col_keys is None:
        return f"{row_part}!T"
    col_part = "_".join(col_keys) if col_keys else "T"
    return f"{row_part}!{col_part}"


def _data_cell_label(cells: list[dict[str, Any]], index: int) -> str:
    """``dataCells[index]`` の ``label`` を取り、欠ければ空文字を返す。"""
    if index >= len(cells):
        return ""
    return cells[index].get("label", "")


def _build_detail_row(
    row: dict[str, Any],
    detail_labels: list[str],
    down_columns: list[tuple[str, str]],
    down_labels: tuple[str, ...],
    across_columns: list[tuple[str, str]],
    across_labels: tuple[str, ...],
) -> dict[str, Any]:
    """factMap 内の ``rows`` の 1 件を、表示名をキーにした dict に変換する。

    グループ列には、そのグループの表示用の ``label`` を入れる。明細列は今と同じく
    ``dataCells[i].label`` を使う（``detailColumnInfo.label`` を ``detail_labels`` 側で
    解いた上でのキー名）。
    """
    out: dict[str, Any] = {}
    cells = row.get("dataCells", []) or []
    for (_, column_label), value in zip_longest(down_columns, down_labels, fillvalue=""):
        out[column_label] = value
    for (_, column_label), value in zip_longest(across_columns, across_labels, fillvalue=""):
        out[column_label] = value
    for index, label in enumerate(detail_labels):
        out[label] = _data_cell_label(cells, index)
    return out


def _prepare_grouped_parse(
    data: dict[str, Any],
    report_id: str,
    allow_truncated: bool,
    *,
    metrics: Any | None,
    report_format: str,
) -> dict[str, Any]:
    """SUMMARY / MATRIX のパースで共通の前処理（切り捨て検査・列の準備）をまとめる。

    戻り値は dict で、SUMMARY と MATRIX のループ処理が同じ部品を取り出せる形にした
    （タプル数が多い + 後段での参照箇所を分かりやすくするため、namedtuple/dataclass より
    dict を採用）。

    Raises:
        SalesforceError: ``detailColumns`` が空のとき（「明細の列が無いレポート」）。
        SalesforceReportTruncatedError: ``allData`` が False で ``allow_truncated`` が False。
    """
    metadata = data.get("reportMetadata", {}) or {}
    extended = data.get("reportExtendedMetadata", {}) or {}
    detail_columns = metadata.get("detailColumns", []) or []
    detail_info = extended.get("detailColumnInfo", {}) or {}

    if not detail_columns:
        raise _report_format_error(report_id, "明細の列が無い")

    detail_labels = [detail_info.get(name, {}).get("label", name) for name in detail_columns]

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

    grouping_info = extended.get("groupingColumnInfo", {}) or {}
    down_columns = _grouping_column_definitions(
        grouping_info,
        (metadata.get("groupingsDown", {}) or {}).get("groupings", []) or [],
    )
    if report_format == MATRIX_FORMAT:
        across_columns = _grouping_column_definitions(
            grouping_info,
            (metadata.get("groupingsAcross", {}) or {}).get("groupings", []) or [],
        )
    else:
        across_columns = []

    down_groupings = (metadata.get("groupingsDown", {}) or {}).get("groupings", []) or []
    if report_format == MATRIX_FORMAT:
        across_groupings = (metadata.get("groupingsAcross", {}) or {}).get("groupings", []) or []
    else:
        across_groupings = []

    columns: list[str] = [column_label for _, column_label in down_columns + across_columns]
    columns.extend(detail_labels)

    return {
        "columns": columns,
        "detail_labels": detail_labels,
        "down_columns": down_columns,
        "across_columns": across_columns,
        "down_groupings": down_groupings,
        "across_groupings": across_groupings,
        "fact_map": data.get("factMap", {}) or {},
    }


def _parse_summary_report(
    data: dict[str, Any],
    report_id: str,
    allow_truncated: bool,
    *,
    metrics: Any | None,
) -> Table:
    """SUMMARY のレスポンスを ``Table`` に変換する。

    各行グループの **リーフ** の ``{key}!T`` を ``factMap`` から取り、合計や中間の
    集計 ``T!T`` / 中間 ``{key}!T`` は無視する（明細の行だけ返すため）。
    """
    ctx = _prepare_grouped_parse(
        data, report_id, allow_truncated, metrics=metrics, report_format=SUMMARY_FORMAT
    )
    rows: list[dict[str, Any]] = []
    for down_keys, down_labels in _walk_groupings(ctx["down_groupings"]):
        key = _factmap_key(down_keys, None)
        entry = ctx["fact_map"].get(key, {}) or {}
        for row in entry.get("rows", []) or []:
            rows.append(
                _build_detail_row(
                    row,
                    ctx["detail_labels"],
                    ctx["down_columns"],
                    down_labels,
                    [],
                    (),
                )
            )
    return Table(ctx["columns"], rows)


def _parse_matrix_report(
    data: dict[str, Any],
    report_id: str,
    allow_truncated: bool,
    *,
    metrics: Any | None,
) -> Table:
    """MATRIX のレスポンスを ``Table`` に変換する。

    各行グループ × 各列グループの **リーフ** から ``{行key}!{列key}`` の
    ``factMap`` を取り、合計や中間の集計は無視する。
    列グループ定義が無い MATRIX は普通無いが、行だけあるケースに備えて
    列キー無しとして扱う（``T!{key}``）。
    """
    ctx = _prepare_grouped_parse(
        data, report_id, allow_truncated, metrics=metrics, report_format=MATRIX_FORMAT
    )
    across_iter = list(_walk_groupings(ctx["across_groupings"])) or [((), ())]
    rows: list[dict[str, Any]] = []
    for down_keys, down_labels in _walk_groupings(ctx["down_groupings"]):
        for across_keys, across_labels in across_iter:
            key = _factmap_key(down_keys, across_keys)
            entry = ctx["fact_map"].get(key, {}) or {}
            for row in entry.get("rows", []) or []:
                rows.append(
                    _build_detail_row(
                        row,
                        ctx["detail_labels"],
                        ctx["down_columns"],
                        down_labels,
                        ctx["across_columns"],
                        across_labels,
                    )
                )
    return Table(ctx["columns"], rows)


def _parse_grouped_report(
    data: dict[str, Any],
    report_id: str,
    allow_truncated: bool,
    *,
    metrics: Any | None,
    report_format: str,
) -> Table:
    """SUMMARY / MATRIX のレスポンスを ``Table`` に変換する（``report_format`` で分岐）。

    2000 行の上限や集計キー（``T!T`` など）の扱いは TABULAR と同じだが、
    **明細を取るため ``includeDetails=true`` を投げる前提**なので、合計や小計の
    セルは無視し、**一番深いグループの ``rows`` だけ**を明細行として並べる。

    戻り値の ``Table`` の列順は「行グループの列 → 列グループの列（MATRIX のみ）→
    明細列」。 ``detailColumns`` が空のときは「明細の列が無いレポート」なので、
    ``_report_format_error`` と同じ系統のエラーで止める（集計だけのレポートを
    空の Table として「成功」させないため）。
    """
    if report_format == SUMMARY_FORMAT:
        return _parse_summary_report(data, report_id, allow_truncated, metrics=metrics)
    return _parse_matrix_report(data, report_id, allow_truncated, metrics=metrics)


def _parse_tabular_report(
    data: dict[str, Any], report_id: str, allow_truncated: bool, *, metrics: Any | None
) -> Table:
    """TABULAR のレスポンスを ``Table`` に変換する。"""
    metadata = data.get("reportMetadata", {}) or {}
    extended = data.get("reportExtendedMetadata", {}) or {}

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

    columns = metadata.get("detailColumns", []) or []
    column_info = extended.get("detailColumnInfo", {}) or {}
    labels = [column_info.get(column, {}).get("label", column) for column in columns]

    rows = (data.get("factMap", {}) or {}).get(DETAIL_ROWS_KEY, {}).get("rows", []) or []
    return Table(
        labels,
        [
            {
                label: _data_cell_label(row.get("dataCells", []) or [], i)
                for i, label in enumerate(labels)
            }
            for row in rows
        ],
    )


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

    ``reportFormat`` が ``TABULAR`` / ``SUMMARY`` / ``MATRIX`` のいずれでも、
    一番深いグループの ``rows``（明細行）を**平らな 1 枚の Table**に並べて返す。
    それ以外の形式（MULTI_BLOCK など）は対応外なので、エラーで止める（明細行を
    取りに行く API ではないため、無言で空の Table を返さない）。

    Returns:
        表示名の列と行 dict を持つ ``Table``。
    """
    if not isinstance(data, dict):
        return Table([], [])

    metadata = data.get("reportMetadata", {}) or {}
    report_format = metadata.get("reportFormat") or TABULAR_FORMAT

    if report_format not in SUPPORTED_REPORT_FORMATS:
        # 形式の判定は「取りに行く明細の単位」が違うだけで、誤って許可すると
        # 無言で 0 行を返す事故になるため明示的に止める
        raise _report_format_error(report_id, str(report_format))

    if report_format == TABULAR_FORMAT:
        return _parse_tabular_report(data, report_id, allow_truncated, metrics=metrics)
    return _parse_grouped_report(
        data, report_id, allow_truncated, metrics=metrics, report_format=report_format
    )


class ReportAPI:
    """レポートを実行して明細行を取得する。

    `SalesforceBase` が `report` 属性として持っている。単体では作らない。

        with Solution() as sf:
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
        body: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | list[Any] | str | None, dict[str, str]]:
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
                raise _report_access_denied_error(report_id, exc.status_code, exc.detail) from exc
            raise

    @measure
    def get(
        self,
        report_id: str,
        filters: list[dict[str, Any]] | None = None,
        allow_truncated: bool = False,
    ) -> Table:
        """レポートを同期実行して明細行を ``Table`` で返す（上限 2000 行）。

        TABULAR / SUMMARY / MATRIX の 3 形式に対応し、**どの形式でも明細行を
        一覧の Table** に並べて返す（サマリー・マトリックスは ``includeDetails=true``
        を投げて、``groupingsDown`` / ``groupingsAcross`` の各リーフの ``rows`` を
        集める）。列は HTTP レスポンスの ``detailColumns`` から組み立てた表示名を
        使い、**0 件のときも列情報が落ちない**。

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
            SalesforceError: 対応外形式（MULTI_BLOCK など）の場合、または
                サマリー・マトリックスで ``detailColumns`` が空（明細の列が無い）
                の場合。
            SalesforceError: レポート API への権限が無い場合
                （HTTP 401 / 403）。
        """
        return self._fetch_report_table(report_id, filters, allow_truncated)

    @measure
    def run_csv(
        self,
        report_id: str,
        path: str | Path,
        filters: list[dict[str, Any]] | None = None,
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
            SalesforceError: 対応外形式、または明細の列が無い場合
                （``get()`` から伝播）。
            SalesforceError: レポート API への権限が無い場合
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
        filters: list[dict[str, Any]] | None = None,
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
            SalesforceError: 対応外形式、または明細の列が無い場合。
            SalesforceError: Salesforce 側で実行が失敗した場合。
            SalesforceError: レポート API への権限が無い場合
                （HTTP 401 / 403）。
            TimeoutError: 制限時間内に完了しなかった場合。
        """
        instances_path = f"{self._base_path()}/{report_id}/instances"
        body: dict[str, Any] = _with_include_details_body(
            {"reportMetadata": {"reportFilters": filters}} if filters else None
        )
        started, _ = self._request(report_id, "POST", instances_path, body=body)
        instance_id = started["id"] if isinstance(started, dict) else ""

        deadline = time.monotonic() + ASYNC_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            data, _ = self._request(
                report_id,
                "GET",
                _with_include_details_query(f"{instances_path}/{instance_id}"),
            )
            status = data.get("status") if isinstance(data, dict) else None
            if status == "Success":
                return _parse_report_payload(
                    data, report_id, allow_truncated, metrics=self._client.metrics
                )
            if status == "Error":
                if not isinstance(data, dict):
                    raise _report_execution_error(report_id, "詳細情報なし")
                detail = str(data.get("error", data.get("message", "詳細情報なし")))
                raise _report_execution_error(report_id, detail)
            time.sleep(POLL_INTERVAL_SECONDS)

        raise TimeoutError(
            f"レポートの取得が {ASYNC_TIMEOUT_SECONDS} 秒以内に終わりませんでした: {report_id}\n"
            "レポートの対象期間を狭めるか、SOQL（query）で取得してください。"
        )

    @measure
    def describe(self, report_id: str) -> dict[str, Any]:
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
                - ``groupingsDown`` / ``groupingsAcross``: サマリー・マトリックスの
                  グループ定義
            - ``reportExtendedMetadata``: 列の表示名・ラベルなど
                - ``detailColumnInfo``: 各列の表示名
                - ``groupingColumnInfo``: グループ列の表示名

            API が dict 以外を返した場合（パース失敗時など）は空 dict。

        Raises:
            SalesforceError: レポート API への権限が無い場合
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
        filters: list[dict[str, Any]] | None,
        allow_truncated: bool,
    ) -> Table:
        """HTTP 取得とパースを行い ``Table`` を返す。

        サマリー・マトリックスの明細行も ``groupingsDown`` / ``groupingsAcross`` の
        リーフに分けて入っているので、``includeDetails=true`` を必ず付ける。
        GET のときは URL クエリで、POST（filters）のときは body で渡す形にしてある。
        """
        path = _with_include_details_query(f"{self._base_path()}/{report_id}")
        logger.debug("Salesforce Report取得開始: Report ID=%s", report_id)
        if filters:
            data, _ = self._request(
                report_id,
                "POST",
                path,
                body=_with_include_details_body({"reportMetadata": {"reportFilters": filters}}),
            )
        else:
            data, _ = self._request(report_id, "GET", path)
        logger.debug("Salesforce APIレスポンス受信: Report ID=%s", report_id)
        table = _parse_report_payload(
            data, report_id, allow_truncated, metrics=self._client.metrics
        )
        logger.debug("Salesforce Report取得完了: Report ID=%s 件数=%d", report_id, len(table))
        return table
