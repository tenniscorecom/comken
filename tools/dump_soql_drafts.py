"""管理表に登録された全レポートについて、SOQLへの書き換え下書きを CSV にダンプする。

**このファイルは開発用。** ``comken`` パッケージの ``__all__`` には載せず、
恒久的な公開 API にもしない。

**旧 ``tools/dump_report_filters.py`` を統合した版。** 元は「1フィルタ=1行」で
``reportFilters`` の生データだけを出す別ツールだったが、どちらも ``describe()`` を
呼ぶため2つ実行すると2重に叩くことになる。SOQLドラフトの組み立てに必要な
``reportFilters`` はこちらでも取得済みなので、生データも「フィルタ詳細(生データ)」
列としてまとめて1回の実行で出す。

Report Describe と Object Describe の結果から ``SELECT`` / ``WHERE`` 句のドラフトを
機械的に組み立て、1レポート1行の CSV へ出す。確認した列マッピングは別のカタログへ
蓄積し、同じ組織・レポートタイプの新規レポートでも再利用する。**完成品ではない。**
演算子の変換は
``docs/salesforce-downloader.md`` の「SOQLレポート」節にある対応表と同じ内容だが、
本物の Salesforce 組織に対して未検証。1対1変換できないもの（``includes`` /
``excludes`` / ``within`` / ``crossFilters`` / 相対期間の ``standardDateFilter`` など）は
SOQL欄を空にして ``BLOCKED`` とする。人が確認してから
``comken/services/salesforce_downloader/soql_reports/`` 配下の ``SoqlReport``
サブクラスへ書き写す前提の道具（docs 手順3〜5に相当する下準備）。

使い方:
    python tools/dump_soql_drafts.py
    python tools/dump_soql_drafts.py --master reports.xlsx

出力先は CLI 引数ではなく、このファイル冒頭の ``OUTPUT_PATH`` を直接書き換える。

**300 件近いレポートを処理するため、組織ごとに接続を使い回す。** 1 件ごとに
``with site() as sf:`` を呼ぶと、認証・接続のたびに数秒を失うため、組織で
グルーピングして 1 組織 1 接続にまとめる。
"""

import argparse
import csv
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

# スクリプトとして実行すると sys.path の先頭は tools/ になるため、
# comken を import する前にリポジトリルートを探索対象へ加える。
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from comken.constants import Encoding  # noqa: E402
from comken.core.table import Table  # noqa: E402
from comken.services.salesforce_downloader.master import ReportEntry, load_master  # noqa: E402
from comken.toolbox.salesforce.sites import site_for  # noqa: E402

logger = logging.getLogger(__name__)

# 出力 CSV の見出し。すべて日本語で、利用者が Excel で開いてそのまま読める形にする
CSV_HEADERS = (
    "管理番号",
    "概要",
    "レポートID",
    "URL",
    "状態",
    "SOQLドラフト",
    "備考",
    "フィルタ詳細(生データ)",
)
CATALOG_HEADERS = (
    "サイトクラス",
    "レポートタイプ",
    "列キー",
    "表示名",
    "フィールドAPI名",
    "型",
    "確認状態",
    "備考",
)

# 出力先 CSV パス。CLI 引数にはせず、直接ここを書き換えて使う。
# 列マッピングの確認結果は同じフォルダのカタログへ蓄積し、次回以降も再利用する。
OUTPUT_PATH = Path("soql_drafts_dump.csv")
# describe() が失敗したとき、「備考」列にこのプレフィックスを付けて失敗事実を残す
FAILED_PREFIX = "取得失敗: "

# 1 組織あたり何件処理したかをログに出す区切り
PROGRESS_LOG_INTERVAL = 50

# reportFilters の operator → SOQL 演算子への対応。
# 正本は docs/salesforce-downloader.md の「SOQLレポート」節にある表。
# 表を変えたらこちらも合わせて直す（二重管理を避けるため、内容は完全に一致させる）。
# ここに無い演算子（includes / excludes / within など）は 1 対 1 変換できないため
# 「備考」へ回し、機械変換しない。
_COMPARISON_OPERATORS = {
    "equals": "=",
    "notEqual": "!=",
    "lessThan": "<",
    "greaterThan": ">",
    "lessOrEqual": "<=",
    "greaterOrEqual": ">=",
}
# LIKE 系（値は常に文字列として '...' で囲む）
_LIKE_OPERATORS = {"contains", "startsWith"}

_UNRESOLVED_FIELD = "(不明)"
_NUMERIC_RE = re.compile(r"-?\d+(\.\d+)?")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_DATETIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})")
_BOOLEAN_TOKEN_RE = re.compile(r"\d+|AND|OR|NOT|\(|\)", re.IGNORECASE)
_NUMBER_TYPES = {"currency", "double", "int", "long", "percent"}
_STRING_TYPES = {
    "string",
    "id",
    "reference",
    "picklist",
    "multipicklist",
    "textarea",
    "url",
    "email",
    "phone",
    "encryptedstring",
}


# キーに "(" "）" を含めるため、class 構文ではなく関数形式の TypedDict を使う
# （class 構文はキーが Python の識別子である必要があるため）。
_DraftRow = TypedDict(
    "_DraftRow",
    {
        "管理番号": str,
        "概要": str,
        "レポートID": str,
        "URL": str,
        "状態": str,
        "SOQLドラフト": str,
        "備考": str,
        "フィルタ詳細(生データ)": str,
    },
)


@dataclass(frozen=True)
class _DraftResult:
    """1レポート分の変換結果。"""

    soql: str
    note: str
    raw_filters: str
    status: str
    catalog_rows: list[dict[str, str]]


class _BooleanFilterParser:
    """Salesforceの番号付きフィルタ論理式をSOQL条件へ展開する。"""

    def __init__(self, tokens: list[str], conditions: dict[int, str]) -> None:
        self._tokens = tokens
        self._conditions = conditions
        self._position = 0

    def parse(self) -> str | None:
        """式全体を解析する。不正な構文や未解決番号があれば ``None`` を返す。"""
        result = self._parse_or()
        if result is None or self._position != len(self._tokens):
            return None
        return result

    def _parse_primary(self) -> str | None:
        if self._position >= len(self._tokens):
            return None
        token = self._tokens[self._position].upper()
        if token == "NOT":
            self._position += 1
            nested = self._parse_primary()
            return f"NOT ({nested})" if nested is not None else None
        if token == "(":
            self._position += 1
            nested = self._parse_or()
            if (
                nested is None
                or self._position >= len(self._tokens)
                or self._tokens[self._position] != ")"
            ):
                return None
            self._position += 1
            return f"({nested})"
        if not token.isdigit():
            return None
        self._position += 1
        condition = self._conditions.get(int(token))
        return f"({condition})" if condition is not None else None

    def _parse_and(self) -> str | None:
        left = self._parse_primary()
        while (
            left is not None
            and self._position < len(self._tokens)
            and self._tokens[self._position].upper() == "AND"
        ):
            self._position += 1
            right = self._parse_primary()
            if right is None:
                return None
            left = f"{left} AND {right}"
        return left

    def _parse_or(self) -> str | None:
        left = self._parse_and()
        while (
            left is not None
            and self._position < len(self._tokens)
            and self._tokens[self._position].upper() == "OR"
        ):
            self._position += 1
            right = self._parse_and()
            if right is None:
                return None
            left = f"{left} OR {right}"
        return left


def _group_entries_by_site(
    entries: dict[str, ReportEntry],
) -> list[tuple[type, list[ReportEntry]]]:
    """``site_for(url)`` で組織を解決し、同じ組織のレポートをまとめる。

    戻り値は「(組織クラス, その組織のレポート一覧)」のタプルのリスト。
    組織の登録順を保つため ``defaultdict(list)`` ではなく ``dict`` を使い、
    出現順を保持する。各値のリストも ``entries`` の挿入順を維持する。
    """
    grouped: dict[type, list[ReportEntry]] = {}
    for entry in entries.values():
        site_class = site_for(entry.url)
        grouped.setdefault(site_class, []).append(entry)
    return list(grouped.items())


def _stringify_filter_field(value: object) -> str:
    """``reportFilters`` の1フィールドを CSV セル用に文字列化する。

    ``value`` にリスト・辞書が入ることがある（例: ``in`` 演算子）。``None`` は
    空文字（「値が無い」と「未取得」を同じ空文字で表現する）。
    """
    return "" if value is None else str(value)


def _format_raw_filters(report_filters: list[object]) -> str:
    """``reportFilters`` を「列=演算子:値」の一覧文字列にする（旧ツールの生データ出力相当）。

    SOQL ドラフトが「不明な列は除外」「個別対応が必要な演算子は除外」と加工済みなのに対し、
    こちらは加工前の全件をそのまま残す（ドラフトの検証・手動での組み立てに使う）。
    """
    if not report_filters:
        return ""
    parts: list[str] = []
    for report_filter in report_filters:
        if not isinstance(report_filter, dict):
            parts.append("(不正な要素)")
            continue
        column = _stringify_filter_field(report_filter.get("column"))
        operator = _stringify_filter_field(report_filter.get("operator"))
        value = _stringify_filter_field(report_filter.get("value"))
        parts.append(f"{column}={operator}:{value}")
    return "; ".join(parts)


def _quote_value(value: str, field_type: str) -> str | None:
    """SOQL 条件式の右辺用に値を整形する。

    Object Describe の型に従い、数値・Boolean・date/datetime は引用せず、文字列・ID・
    参照などは ``'...'`` で囲む。型と値が合わない場合は ``None`` を返す。
    """
    stripped = value.strip()
    normalized_type = field_type.lower()
    if normalized_type in _NUMBER_TYPES:
        return stripped if _NUMERIC_RE.fullmatch(stripped) else None
    if normalized_type == "boolean":
        return stripped.lower() if stripped.lower() in {"true", "false"} else None
    if normalized_type == "date":
        return stripped if _DATE_RE.fullmatch(stripped) else None
    if normalized_type == "datetime":
        return stripped if _DATETIME_RE.fullmatch(stripped) else None
    if normalized_type not in _STRING_TYPES:
        return None
    escaped = stripped.replace("'", "\\'")
    return f"'{escaped}'"


def _filter_to_condition(field: str, field_type: str, operator: str, value: str) -> str | None:
    """1つの reportFilter を SOQL 条件式へ変換する。

    1 対 1 変換できない演算子（``includes`` / ``excludes`` / ``within`` など）は
    ``None`` を返す（呼び出し側が「備考」へ回す）。
    """
    soql_operator = _COMPARISON_OPERATORS.get(operator)
    if soql_operator is not None:
        literal = _quote_value(value, field_type)
        return f"{field} {soql_operator} {literal}" if literal is not None else None
    if operator in _LIKE_OPERATORS:
        if field_type.lower() not in _STRING_TYPES:
            return None
        escaped = value.strip().replace("'", "\\'")
        pattern = f"%{escaped}%" if operator == "contains" else f"{escaped}%"
        return f"{field} LIKE '{pattern}'"
    if operator == "notContain":
        if field_type.lower() not in _STRING_TYPES:
            return None
        escaped = value.strip().replace("'", "\\'")
        return f"NOT ({field} LIKE '%{escaped}%')"
    return None


def _field_map(fields_table: Table) -> dict[str, tuple[str, str]]:
    """``describe_fields()`` の結果から ``列キー -> 対応フィールドAPI名`` の対応表を作る。

    ``対応フィールドAPI名`` が ``(不明)`` の列も、そのまま値として残す
    （呼び出し側で ``_UNRESOLVED_FIELD`` と比較して除外する）。
    """
    return {row["列キー"]: (row["対応フィールドAPI名"], row["型"]) for row in fields_table}


def _build_select_clause(
    detail_columns: list[str],
    field_map: dict[str, tuple[str, str]],
    notes: list[str],
) -> str:
    """明細列を ``SELECT`` 句へ変換する。対応フィールドが不明な列は除外し「備考」へ回す。"""
    resolved: list[str] = []
    unresolved: list[str] = []
    for column_key in detail_columns:
        field = field_map.get(column_key, (_UNRESOLVED_FIELD, ""))[0]
        if field == _UNRESOLVED_FIELD:
            unresolved.append(column_key)
            continue
        if field not in resolved:  # 同じフィールドが複数列に対応することがあるため重複を避ける
            resolved.append(field)
    if unresolved:
        notes.append(f"不明列(SELECTから除外): {', '.join(unresolved)}")
    if not resolved:
        notes.append("SELECT列が1件も解決できなかったため Id のみ")
        return "Id"
    return ", ".join(resolved)


def _expand_boolean_filter(expression: str, conditions: dict[int, str]) -> str | None:
    """番号式を検証し、各番号を括弧付き条件へ置換する。"""
    tokens = _BOOLEAN_TOKEN_RE.findall(expression)
    if "".join(tokens).upper() != re.sub(r"\s+", "", expression).upper():
        return None
    return _BooleanFilterParser(tokens, conditions).parse()


def _build_where_clause(
    report_filters: list[object],
    report_boolean_filter: object,
    field_map: dict[str, tuple[str, str]],
    notes: list[str],
) -> tuple[str, bool]:
    """``reportFilters`` を ``WHERE`` 句へ変換する。1対1変換できないものは「備考」へ回す。"""
    conditions: dict[int, str] = {}
    has_unresolved = False
    manual_operators: list[str] = []
    for number, report_filter in enumerate(report_filters, start=1):
        if not isinstance(report_filter, dict):
            notes.append("reportFiltersに想定外の形式の要素があるため無視")
            has_unresolved = True
            continue
        column_key = str(report_filter.get("column", ""))
        operator = str(report_filter.get("operator", ""))
        value = report_filter.get("value")
        field, field_type = field_map.get(column_key, (_UNRESOLVED_FIELD, ""))
        if field == _UNRESOLVED_FIELD:
            notes.append(f"フィルタ列{column_key!r}の対応フィールドが不明のため除外")
            has_unresolved = True
            continue
        condition = _filter_to_condition(
            field, field_type, operator, str(value) if value is not None else ""
        )
        if condition is None:
            manual_operators.append(operator)
            has_unresolved = True
            continue
        conditions[number] = condition
    if manual_operators:
        notes.append(f"個別対応が必要な演算子あり(WHEREから除外): {', '.join(manual_operators)}")
    if has_unresolved:
        return "", False
    if isinstance(report_boolean_filter, str) and report_boolean_filter.strip():
        expanded = _expand_boolean_filter(report_boolean_filter, conditions)
        if expanded is None:
            notes.append(f"reportBooleanFilterを解釈できません: {report_boolean_filter}")
            return "", False
        return expanded, True
    if report_boolean_filter not in (None, ""):
        notes.append("reportBooleanFilterが想定外の形式です")
        return "", False
    return " AND ".join(conditions.values()), True


def _build_date_filter_condition(
    standard_date_filter: object, notes: list[str]
) -> tuple[str, bool]:
    """``standardDateFilter``（期間フィルタ）を SOQL 条件式へ変換する。

    ``durationValue`` が ``CUSTOM`` 以外（相対期間の名前付き指定、例: ``THIS_MONTH``）の
    ときは、Report API の値と SOQL の日付リテラルが1対1で対応するか未検証のため
    機械変換せず「備考」へ回す。``startDate`` / ``endDate`` の明示指定（``CUSTOM`` または
    ``durationValue`` が無いとき）だけを変換する。
    """
    if not standard_date_filter:
        return "", True
    if not isinstance(standard_date_filter, dict):
        notes.append("期間フィルタ(standardDateFilter)が想定外の形式です")
        return "", False
    column = standard_date_filter.get("column")
    duration_value = standard_date_filter.get("durationValue")
    start_date = standard_date_filter.get("startDate")
    end_date = standard_date_filter.get("endDate")
    if not isinstance(column, str) or not column:
        notes.append("期間フィルタ(standardDateFilter)の列を取得できません")
        return "", False
    if duration_value and duration_value != "CUSTOM":
        notes.append(
            f"期間フィルタ(durationValue={duration_value!r})は個別対応が必要(WHEREから除外)"
        )
        return "", False
    if (
        not isinstance(start_date, str)
        or not isinstance(end_date, str)
        or _DATE_RE.fullmatch(start_date) is None
        or _DATE_RE.fullmatch(end_date) is None
    ):
        notes.append("期間フィルタ(standardDateFilter)の開始日・終了日を取得できず除外")
        return "", False
    return f"{column} >= {start_date} AND {column} <= {end_date}", True


def _validate_report_metadata(metadata: object) -> tuple[dict, str] | tuple[None, str]:
    """``describe()`` の戻り値を検証し、``(report_metadata, "")`` か ``(None, エラー文)`` を返す。

    ``TABULAR`` 以外（``SUMMARY`` / ``MATRIX``）や主オブジェクトが特定できない
    ケースも、ここで「対象外」としてエラー文に含める（呼び出し側で早期リターンする）。
    """
    if not isinstance(metadata, dict):
        return None, "describe()の戻り値が不正な形式です"
    report_metadata = metadata.get("reportMetadata", {})
    if not isinstance(report_metadata, dict):
        return None, "reportMetadataが不正な形式です"
    report_format = report_metadata.get("reportFormat", "")
    if report_format != "TABULAR":
        return None, f"reportFormat={report_format!r}のため対象外(SUMMARY/MATRIXは個別対応)"
    report_type = report_metadata.get("reportType")
    if not isinstance(report_type, dict):
        return None, "reportTypeが不正な形式です"
    object_name = report_type.get("type")
    if not isinstance(object_name, str) or not object_name:
        return None, "reportType.typeから主オブジェクトを特定できません"
    return report_metadata, ""


def _compose_soql_draft(
    report_metadata: dict, object_name: str, field_map: dict[str, tuple[str, str]]
) -> tuple[str, list[str], bool]:
    """検証済みの ``reportMetadata`` から SOQL ドラフトを組み立てる。戻り値は ``(SOQL, notes)``。"""
    notes: list[str] = []
    is_complete = True

    detail_columns = report_metadata.get("detailColumns", [])
    if not isinstance(detail_columns, list):
        notes.append("detailColumnsが想定外の形式です")
        detail_columns = []
        is_complete = False
    select_clause = _build_select_clause(detail_columns, field_map, notes)

    report_filters = report_metadata.get("reportFilters", [])
    if not isinstance(report_filters, list):
        notes.append("reportFiltersが想定外の形式です")
        report_filters = []
        is_complete = False
    where_conditions = []
    where_clause, is_where_complete = _build_where_clause(
        report_filters, report_metadata.get("reportBooleanFilter"), field_map, notes
    )
    if where_clause:
        where_conditions.append(where_clause)

    standard_date_filter = report_metadata.get("standardDateFilter")
    date_condition, is_date_complete = _build_date_filter_condition(standard_date_filter, notes)
    if date_condition:
        where_conditions.append(date_condition)
    is_complete = is_complete and is_where_complete and is_date_complete

    cross_filters = report_metadata.get("crossFilters")
    if cross_filters:
        if isinstance(cross_filters, list):
            notes.append("crossFiltersあり(子オブジェクト条件、個別対応が必要)")
        else:
            notes.append("crossFiltersが想定外の形式です")
        is_complete = False

    soql = f"SELECT {select_clause} FROM {object_name}"
    if where_conditions:
        soql += " WHERE " + " AND ".join(where_conditions)
    return soql, notes, is_complete


def _describe_and_build_draft(
    salesforce_client: Any,
    entry: ReportEntry,
    confirmed_mappings: dict[tuple[str, str, str], tuple[str, str]],
    site_name: str,
) -> _DraftResult:
    """1レポート分のSOQLドラフトと再利用可能な列対応候補を作る。

    「フィルタ詳細(生データ)」は ``reportFormat`` が ``TABULAR`` 以外で SOQL
    ドラフトを組み立てられない場合でも、``describe()`` 自体が成功していれば
    取り出す（生データの監査は SOQL 化の対象かどうかに関係なく使えるため）。
    """
    metadata = salesforce_client.report.describe(entry.report_id)
    raw_report_filters = metadata.get("reportMetadata", {}) if isinstance(metadata, dict) else {}
    raw_filter_values = (
        raw_report_filters.get("reportFilters", []) if isinstance(raw_report_filters, dict) else []
    )
    raw_filters = _format_raw_filters(
        raw_filter_values if isinstance(raw_filter_values, list) else []
    )

    report_metadata, error = _validate_report_metadata(metadata)
    if report_metadata is None:
        return _DraftResult("", error, raw_filters, "BLOCKED", [])

    object_name = report_metadata["reportType"]["type"]
    fields_table, object_error_reason = (
        salesforce_client.report._describe_fields_with_object_status(metadata)
    )
    catalog_rows: list[dict[str, str]] = []
    report_type = object_name
    field_map = _field_map(fields_table)
    for row in fields_table:
        catalog_key = (site_name, report_type, row["列キー"])
        confirmed = confirmed_mappings.get(catalog_key)
        if confirmed is not None:
            field_map[row["列キー"]] = confirmed
        field_name, field_type = field_map[row["列キー"]]
        catalog_rows.append(
            {
                "サイトクラス": site_name,
                "レポートタイプ": report_type,
                "列キー": row["列キー"],
                "表示名": row["表示名"],
                "フィールドAPI名": field_name,
                "型": field_type,
                "確認状態": "確認済み" if confirmed is not None else "未確認",
                "備考": "" if confirmed is not None else row["備考"],
            }
        )
    soql, notes, is_complete = _compose_soql_draft(report_metadata, object_name, field_map)
    if object_error_reason is not None:
        notes.insert(0, object_error_reason)
        is_complete = False
    status = "READY" if is_complete and not notes else "REVIEW"
    if not is_complete:
        status = "BLOCKED"
        soql = ""
    return _DraftResult(soql, " / ".join(notes), raw_filters, status, catalog_rows)


def _read_catalog(
    path: Path,
) -> tuple[dict[tuple[str, str, str], tuple[str, str]], list[dict[str, str]]]:
    """既存カタログと、そのうち利用者が確認済みにした対応を読む。"""
    if not path.exists():
        return {}, []
    with path.open(encoding=Encoding.UTF8_SIG, newline="") as file:
        rows = list(csv.DictReader(file))
        confirmed = {
            (row["サイトクラス"], row["レポートタイプ"], row["列キー"]): (
                row["フィールドAPI名"],
                row["型"],
            )
            for row in rows
            if row.get("確認状態") == "確認済み"
            and row.get("フィールドAPI名") not in {None, "", _UNRESOLVED_FIELD}
            and row.get("型")
        }
    return confirmed, rows


def _catalog_key(row: dict[str, str]) -> tuple[str, str, str]:
    """カタログ1行から組織・レポートタイプ・列キーの一意キーを作る。"""
    return row["サイトクラス"], row["レポートタイプ"], row["列キー"]


def _merge_catalog_rows(
    existing_rows: list[dict[str, str]], observed_rows: list[dict[str, str]]
) -> list[dict[str, str]]:
    """確認済み行を守りつつ、自動候補を安全に統合する。"""
    merged = {_catalog_key(row): row for row in existing_rows}
    for observed in observed_rows:
        key = _catalog_key(observed)
        current = merged.get(key)
        if current is None:
            merged[key] = observed
            continue
        if current.get("確認状態") in {"確認済み", "要確認"}:
            continue
        current_mapping = (current.get("フィールドAPI名", ""), current.get("型", ""))
        observed_mapping = (observed["フィールドAPI名"], observed["型"])
        if current_mapping == observed_mapping:
            merged[key] = observed
            continue
        current_resolved = current_mapping[0] not in {"", _UNRESOLVED_FIELD}
        observed_resolved = observed_mapping[0] not in {"", _UNRESOLVED_FIELD}
        if observed_resolved and not current_resolved:
            merged[key] = observed
            continue
        if current_resolved and not observed_resolved:
            continue
        if current_resolved and observed_resolved:
            candidates = sorted(
                {
                    f"{current_mapping[0]}({current_mapping[1] or '型不明'})",
                    f"{observed_mapping[0]}({observed_mapping[1] or '型不明'})",
                }
            )
            merged[key] = {
                **observed,
                "フィールドAPI名": _UNRESOLVED_FIELD,
                "型": "",
                "確認状態": "要確認",
                "備考": f"自動候補が競合: {', '.join(candidates)}",
            }
    return list(merged.values())


def _write_catalog(
    path: Path,
    existing_rows: list[dict[str, str]],
    observed_rows: list[dict[str, str]],
) -> None:
    """確認済みの蓄積を保持したまま、今回観測した候補を保存する。"""
    rows = _merge_catalog_rows(existing_rows, observed_rows)
    with path.open("w", encoding=Encoding.UTF8_SIG, newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CATALOG_HEADERS)
        writer.writeheader()
        writer.writerows(rows)  # type: ignore[arg-type]


def _write_csv(output_path: Path, rows: list[_DraftRow]) -> None:
    """1 行ずつ dict で受け取ったデータを CSV に書き出す。

    Excel で開いて文字化けしないよう BOM 付き UTF-8 (``utf-8-sig``) で書く。
    ``newline=""`` を付けないと Windows で空行が混ざる。
    """
    with output_path.open("w", encoding=Encoding.UTF8_SIG, newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(rows)  # type: ignore[arg-type]


def dump_soql_drafts(
    master_path: str | Path | None,
    output_path: Path,
    catalog_path: Path | None = None,
) -> int:
    """本体。``main()`` とテスト両方から呼ばれる。戻り値は書き出した行数。

    Args:
        master_path: 管理表（Excel）のパス。``None`` のときは ``load_master()`` の既定を使う。
        output_path: 出力先 CSV パス。
        catalog_path: 列マッピングカタログの保存先。``None`` のときは出力先と同じ
            フォルダの ``soql_field_mapping_catalog.csv``。

    Returns:
        CSV に書き出した行数（見出し行は含まない。管理表の件数と同じ）。
    """
    catalog_path = catalog_path or output_path.with_name("soql_field_mapping_catalog.csv")
    confirmed_mappings, existing_catalog_rows = _read_catalog(catalog_path)
    entries = load_master(master_path)
    if not entries:
        logger.warning("管理表に登録されているレポートがありません: %s", master_path)
        _write_csv(output_path, [])
        return 0

    grouped = _group_entries_by_site(entries)
    logger.info("管理表: %d 件 / 組織: %d グループ", len(entries), len(grouped))

    rows: list[_DraftRow] = []
    catalog_rows: list[dict[str, str]] = []
    processed = 0
    total = len(entries)
    for site_class, site_entries in grouped:
        site_written_keys: set[str] = set()
        logger.info(
            "組織 %s: %d 件を処理します",
            getattr(site_class, "DISPLAY_NAME", site_class.__name__),
            len(site_entries),
        )
        try:
            with site_class() as salesforce_client:
                for entry in site_entries:
                    processed += 1
                    if processed % PROGRESS_LOG_INTERVAL == 0 or processed == total:
                        logger.info("処理中: %d/%d 件目 (%s)", processed, total, entry.key)
                    try:
                        result = _describe_and_build_draft(
                            salesforce_client,
                            entry,
                            confirmed_mappings,
                            site_class.__name__,
                        )
                        catalog_rows.extend(result.catalog_rows)
                    except Exception as exc:
                        # 1 件の失敗（権限・削除済み・通信断・想定外バグ）で全体を止めない
                        logger.error("SOQLドラフト作成に失敗しました: %s（%s）", entry.key, exc)
                        rows.append(
                            {
                                "管理番号": entry.key,
                                "概要": entry.summary,
                                "レポートID": entry.report_id,
                                "URL": entry.url,
                                "状態": "ERROR",
                                "SOQLドラフト": "",
                                "備考": f"{FAILED_PREFIX}{exc}",
                                "フィルタ詳細(生データ)": "",
                            }
                        )
                        site_written_keys.add(entry.key)
                        continue
                    rows.append(
                        {
                            "管理番号": entry.key,
                            "概要": entry.summary,
                            "レポートID": entry.report_id,
                            "URL": entry.url,
                            "状態": result.status,
                            "SOQLドラフト": result.soql,
                            "備考": result.note,
                            "フィルタ詳細(生データ)": result.raw_filters,
                        }
                    )
                    site_written_keys.add(entry.key)
        except Exception as exc:
            # 1 組織丸ごと失敗した場合、その組織の登録件すべてを「取得失敗」行として残す
            logger.error(
                "%s への接続に失敗しました: %s",
                getattr(site_class, "DISPLAY_NAME", site_class.__name__),
                exc,
            )
            for entry in site_entries:
                if entry.key in site_written_keys:
                    continue
                rows.append(
                    {
                        "管理番号": entry.key,
                        "概要": entry.summary,
                        "レポートID": entry.report_id,
                        "URL": entry.url,
                        "状態": "ERROR",
                        "SOQLドラフト": "",
                        "備考": f"{FAILED_PREFIX}{exc}",
                        "フィルタ詳細(生データ)": "",
                    }
                )

    _write_csv(output_path, rows)
    _write_catalog(catalog_path, existing_catalog_rows, catalog_rows)
    logger.info(
        "%s へ %d 行を書き出しました（管理表 %d 件）",
        output_path,
        len(rows),
        len(entries),
    )
    return len(rows)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--master",
        type=Path,
        default=None,
        help=(
            "管理表（Excel）のパス。省略時は ``load_master()`` の既定"
            "（``comken.services.salesforce_downloader._paths.MASTER_PATH``）"
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    # 出力先は CLI 引数にせず OUTPUT_PATH を直接書き換える運用にしている
    # （社内移行作業では、毎回オプションを付けるより1箇所直す方が早い）。
    args = _parse_args(argv)
    dump_soql_drafts(args.master, OUTPUT_PATH)
    with OUTPUT_PATH.open(encoding=Encoding.UTF8_SIG, newline="") as file:
        statuses = [row["状態"] for row in csv.DictReader(file)]
    return 1 if "ERROR" in statuses else 0


if __name__ == "__main__":
    raise SystemExit(main())
