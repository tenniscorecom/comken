"""管理表に登録された全レポートについて、SOQLへの書き換え下書きを CSV にダンプする。

**このファイルは開発用**（``tools/dump_report_filters.py`` と同じ位置づけ）。
``comken`` パッケージの ``__all__`` には載せず、恒久的な公開 API にもしない。

``describe()`` / ``describe_fields()`` の結果から ``SELECT`` / ``WHERE`` 句のドラフトを
機械的に組み立て、1レポート1行の CSV へ出す。**完成品ではない。** 演算子の変換は
``docs/salesforce-downloader.md`` の「SOQLレポート」節にある対応表と同じ内容だが、
本物の Salesforce 組織に対して未検証。1対1変換できないもの（``includes`` /
``excludes`` / ``within`` / ``crossFilters`` / 相対期間の ``standardDateFilter`` など）は
機械変換せず「備考」列へ回す。人が確認してから
``comken/services/salesforce_downloader/soql_reports/`` 配下の ``SoqlReport``
サブクラスへ書き写す前提の道具（docs 手順4〜5に相当する下準備）。

使い方:
    python tools/dump_soql_drafts.py
    python tools/dump_soql_drafts.py --master reports.xlsx --output soql_drafts.csv

**300 件近いレポートを処理するため、組織ごとに接続を使い回す。** 組織のグルーピング・
接続の使い回しは ``tools/dump_report_filters.py`` の実装をそのまま使う（同じロジックを
二重管理しない）。
"""

import argparse
import csv
import logging
import re
import sys
from pathlib import Path
from typing import Any, TypedDict

# スクリプトとして実行すると sys.path の先頭は tools/ になるため、
# comken / tools を import する前にリポジトリルートを探索対象へ加える。
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from comken.constants import Encoding  # noqa: E402
from comken.core.table import Table  # noqa: E402
from comken.services.salesforce_downloader.master import ReportEntry, load_master  # noqa: E402
from tools.dump_report_filters import _group_entries_by_site  # noqa: E402

logger = logging.getLogger(__name__)

# 出力 CSV の見出し。すべて日本語で、利用者が Excel で開いてそのまま読める形にする
CSV_HEADERS = ("管理番号", "概要", "レポートID", "URL", "SOQLドラフト", "備考")

DEFAULT_OUTPUT_PATH = Path("soql_drafts_dump.csv")
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


class _DraftRow(TypedDict):
    """CSV 1 行分。"""

    管理番号: str
    概要: str
    レポートID: str
    URL: str
    SOQLドラフト: str
    備考: str


def _quote_value(value: str) -> str:
    """SOQL 条件式の右辺用に値を整形する。

    数値らしい文字列（整数・小数）はそのまま、それ以外は SOQL 文字列リテラルとして
    ``'...'`` で囲む（内部のシングルクォートはエスケープする）。フィールドの実際の型
    までは追わない簡易な判定のため、最終的な妥当性は人が確認する前提。
    """
    stripped = value.strip()
    if _NUMERIC_RE.fullmatch(stripped):
        return stripped
    escaped = stripped.replace("'", "\\'")
    return f"'{escaped}'"


def _filter_to_condition(field: str, operator: str, value: str) -> str | None:
    """1つの reportFilter を SOQL 条件式へ変換する。

    1 対 1 変換できない演算子（``includes`` / ``excludes`` / ``within`` など）は
    ``None`` を返す（呼び出し側が「備考」へ回す）。
    """
    soql_operator = _COMPARISON_OPERATORS.get(operator)
    if soql_operator is not None:
        return f"{field} {soql_operator} {_quote_value(value)}"
    if operator in _LIKE_OPERATORS:
        escaped = value.strip().replace("'", "\\'")
        pattern = f"%{escaped}%" if operator == "contains" else f"{escaped}%"
        return f"{field} LIKE '{pattern}'"
    if operator == "notContain":
        escaped = value.strip().replace("'", "\\'")
        return f"NOT ({field} LIKE '%{escaped}%')"
    return None


def _field_map(fields_table: Table) -> dict[str, str]:
    """``describe_fields()`` の結果から ``列キー -> 対応フィールドAPI名`` の対応表を作る。

    ``対応フィールドAPI名`` が ``(不明)`` の列も、そのまま値として残す
    （呼び出し側で ``_UNRESOLVED_FIELD`` と比較して除外する）。
    """
    return {row["列キー"]: row["対応フィールドAPI名"] for row in fields_table}


def _build_select_clause(
    detail_columns: list[str],
    field_map: dict[str, str],
    notes: list[str],
) -> str:
    """明細列を ``SELECT`` 句へ変換する。対応フィールドが不明な列は除外し「備考」へ回す。"""
    resolved: list[str] = []
    unresolved: list[str] = []
    for column_key in detail_columns:
        field = field_map.get(column_key, _UNRESOLVED_FIELD)
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


def _build_where_clause(
    report_filters: list[object],
    report_boolean_filter: object,
    field_map: dict[str, str],
    notes: list[str],
) -> str:
    """``reportFilters`` を ``WHERE`` 句へ変換する。1対1変換できないものは「備考」へ回す。"""
    conditions: list[str] = []
    manual_operators: list[str] = []
    for report_filter in report_filters:
        if not isinstance(report_filter, dict):
            notes.append("reportFiltersに想定外の形式の要素があるため無視")
            continue
        column_key = str(report_filter.get("column", ""))
        operator = str(report_filter.get("operator", ""))
        value = report_filter.get("value")
        field = field_map.get(column_key, _UNRESOLVED_FIELD)
        if field == _UNRESOLVED_FIELD:
            notes.append(f"フィルタ列{column_key!r}の対応フィールドが不明のため除外")
            continue
        condition = _filter_to_condition(field, operator, str(value) if value is not None else "")
        if condition is None:
            manual_operators.append(operator)
            continue
        conditions.append(condition)
    if manual_operators:
        notes.append(f"個別対応が必要な演算子あり(WHEREから除外): {', '.join(manual_operators)}")
    if isinstance(report_boolean_filter, str) and report_boolean_filter:
        # AND 以外の組み合わせ(OR混在など)の可能性があるため、単純な AND 連結が
        # 実際の論理と一致しない場合がある旨を明記する。
        notes.append(f"reportBooleanFilterあり(単純ANDで連結、要確認): {report_boolean_filter}")
    return " AND ".join(conditions)


def _build_date_filter_condition(standard_date_filter: object, notes: list[str]) -> str | None:
    """``standardDateFilter``（期間フィルタ）を SOQL 条件式へ変換する。

    ``durationValue`` が ``CUSTOM`` 以外（相対期間の名前付き指定、例: ``THIS_MONTH``）の
    ときは、Report API の値と SOQL の日付リテラルが1対1で対応するか未検証のため
    機械変換せず「備考」へ回す。``startDate`` / ``endDate`` の明示指定（``CUSTOM`` または
    ``durationValue`` が無いとき）だけを変換する。
    """
    if not isinstance(standard_date_filter, dict) or not standard_date_filter:
        return None
    column = standard_date_filter.get("column")
    duration_value = standard_date_filter.get("durationValue")
    start_date = standard_date_filter.get("startDate")
    end_date = standard_date_filter.get("endDate")
    if not column:
        return None
    if duration_value and duration_value != "CUSTOM":
        notes.append(
            f"期間フィルタ(durationValue={duration_value!r})は個別対応が必要(WHEREから除外)"
        )
        return None
    if not start_date or not end_date:
        notes.append("期間フィルタ(standardDateFilter)の開始日・終了日を取得できず除外")
        return None
    return f"{column} >= {start_date} AND {column} <= {end_date}"


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
    object_name = report_metadata.get("reportType", {}).get("type", "")
    if not object_name:
        return None, "reportType.typeから主オブジェクトを特定できません"
    return report_metadata, ""


def _compose_soql_draft(
    report_metadata: dict, object_name: str, field_map: dict[str, str]
) -> tuple[str, list[str]]:
    """検証済みの ``reportMetadata`` から SOQL ドラフトを組み立てる。戻り値は ``(SOQL, notes)``。"""
    notes: list[str] = []

    detail_columns = report_metadata.get("detailColumns", [])
    if not isinstance(detail_columns, list):
        detail_columns = []
    select_clause = _build_select_clause(detail_columns, field_map, notes)

    report_filters = report_metadata.get("reportFilters", [])
    if not isinstance(report_filters, list):
        report_filters = []
    where_conditions = []
    where_clause = _build_where_clause(
        report_filters, report_metadata.get("reportBooleanFilter"), field_map, notes
    )
    if where_clause:
        where_conditions.append(where_clause)

    date_condition = _build_date_filter_condition(report_metadata.get("standardDateFilter"), notes)
    if date_condition:
        where_conditions.append(date_condition)

    cross_filters = report_metadata.get("crossFilters")
    if isinstance(cross_filters, list) and cross_filters:
        notes.append("crossFiltersあり(子オブジェクト条件、個別対応が必要)")

    soql = f"SELECT {select_clause} FROM {object_name}"
    if where_conditions:
        soql += " WHERE " + " AND ".join(where_conditions)
    return soql, notes


def _describe_and_build_draft(salesforce_client: Any, entry: ReportEntry) -> tuple[str, str]:
    """1レポート分の SOQL ドラフトを組み立てる。戻り値は ``(SOQLドラフト, 備考)``。"""
    metadata = salesforce_client.report.describe(entry.report_id)
    report_metadata, error = _validate_report_metadata(metadata)
    if report_metadata is None:
        return "", error

    object_name = report_metadata["reportType"]["type"]
    fields_table = salesforce_client.report.describe_fields(entry.report_id)
    field_map = _field_map(fields_table)

    soql, notes = _compose_soql_draft(report_metadata, object_name, field_map)
    return soql, " / ".join(notes)


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
) -> int:
    """本体。``main()`` とテスト両方から呼ばれる。戻り値は書き出した行数。

    Args:
        master_path: 管理表（Excel）のパス。``None`` のときは ``load_master()`` の既定を使う。
        output_path: 出力先 CSV パス。

    Returns:
        CSV に書き出した行数（見出し行は含まない。管理表の件数と同じ）。
    """
    entries = load_master(master_path)
    if not entries:
        logger.warning("管理表に登録されているレポートがありません: %s", master_path)
        _write_csv(output_path, [])
        return 0

    grouped = _group_entries_by_site(entries)
    logger.info("管理表: %d 件 / 組織: %d グループ", len(entries), len(grouped))

    rows: list[_DraftRow] = []
    processed = 0
    total = len(entries)
    for site_class, site_entries in grouped:
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
                        soql, note = _describe_and_build_draft(salesforce_client, entry)
                    except Exception as exc:
                        # 1 件の失敗（権限・削除済み・通信断・想定外バグ）で全体を止めない
                        logger.error("SOQLドラフト作成に失敗しました: %s（%s）", entry.key, exc)
                        rows.append(
                            _DraftRow(
                                管理番号=entry.key,
                                概要=entry.summary,
                                レポートID=entry.report_id,
                                URL=entry.url,
                                SOQLドラフト="",
                                備考=f"{FAILED_PREFIX}{exc}",
                            )
                        )
                        continue
                    rows.append(
                        _DraftRow(
                            管理番号=entry.key,
                            概要=entry.summary,
                            レポートID=entry.report_id,
                            URL=entry.url,
                            SOQLドラフト=soql,
                            備考=note,
                        )
                    )
        except Exception as exc:
            # 1 組織丸ごと失敗した場合、その組織の登録件すべてを「取得失敗」行として残す
            logger.error(
                "%s への接続に失敗しました: %s",
                getattr(site_class, "DISPLAY_NAME", site_class.__name__),
                exc,
            )
            for entry in site_entries:
                rows.append(
                    _DraftRow(
                        管理番号=entry.key,
                        概要=entry.summary,
                        レポートID=entry.report_id,
                        URL=entry.url,
                        SOQLドラフト="",
                        備考=f"{FAILED_PREFIX}{exc}",
                    )
                )

    _write_csv(output_path, rows)
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
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"出力先 CSV パス（既定 {DEFAULT_OUTPUT_PATH}）",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    dump_soql_drafts(args.master, args.output)
    return 0


if __name__ == "__main__":
    main()
