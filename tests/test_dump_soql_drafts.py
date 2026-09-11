"""``tools/dump_soql_drafts.py`` のテスト。

Salesforce には繋がず、管理表は ``tmp_path`` 配下に作って実物を読み込ませ、
``site_for()`` は ``unittest.mock.patch`` で差し替える。
"""

import csv
from pathlib import Path
from unittest.mock import MagicMock, patch

from comken.core.table import Table
from comken.toolbox.excel import Excel
from tools.dump_soql_drafts import (
    CSV_HEADERS,
    FAILED_PREFIX,
    _expand_boolean_filter,
    _filter_to_condition,
    _merge_catalog_rows,
    dump_soql_drafts,
)

URL_A = "https://example--sandbox.sandbox.my.salesforce.com/lightning/r/Report/00O5g00000ABCDE/view"
URL_B = "https://example.my.salesforce.com/lightning/r/Report/00O5g00000FGHIJ/view"

HEADERS = [
    "ID",
    "グループ名",
    "担当者",
    "概要",
    "Salesforce URL",
    "保存先",
    "有効",
    "備考",
]

FIELDS_COLUMNS = ["列キー", "表示名", "対応フィールドAPI名", "型", "備考"]


def make_master(path: Path, rows: list[list]) -> Path:
    """テスト用の管理表（Excel）を作る。"""
    table_rows = [dict(zip(HEADERS, row, strict=True)) for row in rows]
    with Excel(path) as book:
        book.create_data_sheet("管理表").create_table("管理表", Table(HEADERS, table_rows))
    return path


def fake_site(
    describe_response: object | Exception, fields_table: Table | None = None
) -> MagicMock:
    """``describe()`` / ``describe_fields()`` が固定レスポンスを返す Salesforce クライアント。"""
    site_class = MagicMock()
    client = MagicMock()
    report = client.__enter__.return_value.report
    if isinstance(describe_response, Exception):
        report.describe.side_effect = describe_response
    else:
        report.describe.return_value = describe_response
    table = fields_table or Table(FIELDS_COLUMNS, [])
    report.describe_fields_with_object_status.return_value = (table, None)
    report.describe_fields.return_value = table
    site_class.return_value = client
    site_class.__name__ = "FakeSite"
    site_class.DISPLAY_NAME = "テスト組織"
    return site_class


def _master_with_one_report(tmp_path: Path, url: str = URL_A) -> Path:
    return make_master(
        tmp_path / "管理表.xlsx",
        [["1001", "営業事務グループ", "山田", "対象レポート", url, str(tmp_path), "○", ""]],
    )


def _read_rows(output: Path) -> list[dict[str, str]]:
    with output.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


class TestSoqlDraftBuilding:
    """TABULAR レポートから SELECT/WHERE のドラフトを組み立てること。"""

    def test_builds_select_and_where_from_resolved_fields(self, tmp_path):
        master = _master_with_one_report(tmp_path)
        output = tmp_path / "out.csv"
        describe_response = {
            "reportMetadata": {
                "reportFormat": "TABULAR",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPP_NAME", "AMOUNT"],
                "reportFilters": [
                    {"column": "STAGE", "operator": "equals", "value": "Closed Won"},
                ],
            }
        }
        fields_table = Table(
            FIELDS_COLUMNS,
            [
                {
                    "列キー": "OPP_NAME",
                    "表示名": "案件名",
                    "対応フィールドAPI名": "Name",
                    "型": "string",
                    "備考": "",
                },
                {
                    "列キー": "AMOUNT",
                    "表示名": "金額",
                    "対応フィールドAPI名": "Amount",
                    "型": "currency",
                    "備考": "",
                },
                {
                    "列キー": "STAGE",
                    "表示名": "ステージ",
                    "対応フィールドAPI名": "StageName",
                    "型": "picklist",
                    "備考": "",
                },
            ],
        )
        site = fake_site(describe_response, fields_table)
        with patch("tools.dump_soql_drafts.site_for", return_value=site):
            written = dump_soql_drafts(master, output)
        assert written == 1
        rows = _read_rows(output)
        assert list(rows[0].keys()) == list(CSV_HEADERS)
        assert rows[0]["管理番号"] == "1001"
        assert rows[0]["レポートID"] == "00O5g00000ABCDE"
        assert (
            rows[0]["SOQLドラフト"]
            == "SELECT Name, Amount FROM Opportunity WHERE StageName = 'Closed Won'"
        )
        assert rows[0]["備考"] == ""
        report_api = site.return_value.__enter__.return_value.report
        assert report_api.describe.call_count == 1

    def test_confirmed_catalog_mapping_is_prioritized(self, tmp_path):
        master = _master_with_one_report(tmp_path)
        output = tmp_path / "out.csv"
        catalog = tmp_path / "catalog.csv"
        with catalog.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(
                [
                    "サイトクラス",
                    "レポートタイプ",
                    "列キー",
                    "表示名",
                    "フィールドAPI名",
                    "型",
                    "確認状態",
                    "備考",
                ]
            )
            writer.writerow(
                [
                    "FakeSite",
                    "Opportunity",
                    "CUSTOM",
                    "独自列",
                    "Custom__c",
                    "string",
                    "確認済み",
                    "",
                ]
            )
        describe_response = {
            "reportMetadata": {
                "reportFormat": "TABULAR",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["CUSTOM"],
                "reportFilters": [],
            }
        }
        fields_table = Table(
            FIELDS_COLUMNS,
            [
                {
                    "列キー": "CUSTOM",
                    "表示名": "独自列",
                    "対応フィールドAPI名": "(不明)",
                    "型": "",
                    "備考": "対応フィールドなし",
                }
            ],
        )
        site = fake_site(describe_response, fields_table)
        with patch("tools.dump_soql_drafts.site_for", return_value=site):
            dump_soql_drafts(master, output, catalog)

        assert _read_rows(output)[0]["SOQLドラフト"] == "SELECT Custom__c FROM Opportunity"

    def test_unverified_from_object_is_blocked_even_with_resolved_columns(self, tmp_path):
        master = _master_with_one_report(tmp_path)
        output = tmp_path / "out.csv"
        describe_response = {
            "reportMetadata": {
                "reportFormat": "TABULAR",
                "reportType": {"type": "CustomReportType"},
                "detailColumns": ["NAME"],
                "reportFilters": [],
            }
        }
        fields_table = Table(
            FIELDS_COLUMNS,
            [
                {
                    "列キー": "NAME",
                    "表示名": "名前",
                    "対応フィールドAPI名": "Name",
                    "型": "string",
                    "備考": "",
                }
            ],
        )
        site = fake_site(describe_response, fields_table)
        report = site.return_value.__enter__.return_value.report
        report.describe_fields_with_object_status.return_value = (
            fields_table,
            "主オブジェクトを検証できません",
        )

        with patch("tools.dump_soql_drafts.site_for", return_value=site):
            dump_soql_drafts(master, output)

        row = _read_rows(output)[0]
        assert row["状態"] == "BLOCKED"
        assert row["SOQLドラフト"] == ""
        assert "主オブジェクト" in row["備考"]

    def test_numeric_value_is_not_quoted(self, tmp_path):
        """数値らしい値は SOQL 上でクォートしない。"""
        master = _master_with_one_report(tmp_path)
        output = tmp_path / "out.csv"
        describe_response = {
            "reportMetadata": {
                "reportFormat": "TABULAR",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["AMOUNT"],
                "reportFilters": [
                    {"column": "AMOUNT", "operator": "greaterThan", "value": "1000"},
                ],
            }
        }
        fields_table = Table(
            FIELDS_COLUMNS,
            [
                {
                    "列キー": "AMOUNT",
                    "表示名": "金額",
                    "対応フィールドAPI名": "Amount",
                    "型": "currency",
                    "備考": "",
                },
            ],
        )
        site = fake_site(describe_response, fields_table)
        with patch("tools.dump_soql_drafts.site_for", return_value=site):
            dump_soql_drafts(master, output)
        rows = _read_rows(output)
        assert rows[0]["SOQLドラフト"] == "SELECT Amount FROM Opportunity WHERE Amount > 1000"

    def test_no_filters_produces_select_only(self, tmp_path):
        master = _master_with_one_report(tmp_path)
        output = tmp_path / "out.csv"
        describe_response = {
            "reportMetadata": {
                "reportFormat": "TABULAR",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPP_NAME"],
                "reportFilters": [],
            }
        }
        fields_table = Table(
            FIELDS_COLUMNS,
            [
                {
                    "列キー": "OPP_NAME",
                    "表示名": "案件名",
                    "対応フィールドAPI名": "Name",
                    "型": "string",
                    "備考": "",
                },
            ],
        )
        site = fake_site(describe_response, fields_table)
        with patch("tools.dump_soql_drafts.site_for", return_value=site):
            dump_soql_drafts(master, output)
        rows = _read_rows(output)
        assert rows[0]["SOQLドラフト"] == "SELECT Name FROM Opportunity"


class TestUnsupportedReportFormat:
    def test_format_without_report_type_stays_blocked(self, tmp_path):
        """reportFormatに関わらず、主オブジェクトが特定できなければBLOCKED。"""
        master = _master_with_one_report(tmp_path)
        output = tmp_path / "out.csv"
        describe_response = {"reportMetadata": {"reportFormat": "SUMMARY"}}
        site = fake_site(describe_response)
        with patch("tools.dump_soql_drafts.site_for", return_value=site):
            dump_soql_drafts(master, output)
        row = _read_rows(output)[0]
        assert row["SOQLドラフト"] == ""
        assert row["状態"] == "BLOCKED"

    def test_summary_format_exposes_raw_aggregation_data(self, tmp_path):
        """SUMMARY形式でSOQLは作れなくても、aggregates/groupingsDownの生データは見える。"""
        master = _master_with_one_report(tmp_path)
        output = tmp_path / "out.csv"
        describe_response = {
            "reportMetadata": {
                "reportFormat": "SUMMARY",
                "aggregates": ["s!AMOUNT"],
                "groupingsDown": [{"name": "STAGE_NAME", "sortOrder": "Asc"}],
            }
        }
        site = fake_site(describe_response)
        with patch("tools.dump_soql_drafts.site_for", return_value=site):
            dump_soql_drafts(master, output)
        row = _read_rows(output)[0]
        assert row["SOQLドラフト"] == ""
        detail = row["集計・グルーピング詳細(生データ)"]
        assert "aggregates:" in detail
        assert "s!AMOUNT" in detail
        assert "groupingsDown:" in detail
        assert "STAGE_NAME" in detail
        # 辞書のリストをそのまま str() でダンプした読みにくい形
        # （例: "[{'name': 'STAGE_NAME', ...}]"）になっていないことを確認する
        assert "{'name'" not in detail
        assert detail == "aggregates: s!AMOUNT | groupingsDown: STAGE_NAME(Asc)"

    def test_matrix_format_exposes_groupings_across(self, tmp_path):
        """MATRIX形式はgroupingsAcross（列側のグルーピング）も生データに含む。"""
        master = _master_with_one_report(tmp_path)
        output = tmp_path / "out.csv"
        describe_response = {
            "reportMetadata": {
                "reportFormat": "MATRIX",
                "groupingsDown": [{"name": "STAGE_NAME"}],
                "groupingsAcross": [{"name": "CLOSE_DATE"}],
            }
        }
        site = fake_site(describe_response)
        with patch("tools.dump_soql_drafts.site_for", return_value=site):
            dump_soql_drafts(master, output)
        detail = _read_rows(output)[0]["集計・グルーピング詳細(生データ)"]
        assert "groupingsDown:" in detail
        assert "groupingsAcross:" in detail
        assert "CLOSE_DATE" in detail

    def test_tabular_without_aggregation_leaves_column_empty(self, tmp_path):
        """TABULARで集計・グルーピングが無ければ、その列は空のまま。"""
        master = _master_with_one_report(tmp_path)
        output = tmp_path / "out.csv"
        describe_response = {
            "reportMetadata": {
                "reportFormat": "TABULAR",
                "reportType": {"type": "Opportunity"},
                "detailColumns": [],
                "reportFilters": [],
            }
        }
        site = fake_site(describe_response)
        with patch("tools.dump_soql_drafts.site_for", return_value=site):
            dump_soql_drafts(master, output)
        assert _read_rows(output)[0]["集計・グルーピング詳細(生データ)"] == ""


class TestRawFilterDetails:
    """「フィルタ詳細(生データ)」列(旧 dump_report_filters.py 相当)のテスト。"""

    def test_raw_filters_are_listed_regardless_of_soql_conversion(self, tmp_path):
        """ドラフトSOQLでは除外された演算子(includes)も、生データ列には残ること。"""
        master = _master_with_one_report(tmp_path)
        output = tmp_path / "out.csv"
        describe_response = {
            "reportMetadata": {
                "reportFormat": "TABULAR",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPP_NAME"],
                "reportFilters": [
                    {"column": "STAGE", "operator": "equals", "value": "Closed Won"},
                    {"column": "TYPE", "operator": "includes", "value": ["A", "B"]},
                ],
            }
        }
        fields_table = Table(
            FIELDS_COLUMNS,
            [
                {
                    "列キー": "OPP_NAME",
                    "表示名": "案件名",
                    "対応フィールドAPI名": "Name",
                    "型": "string",
                    "備考": "",
                },
                {
                    "列キー": "STAGE",
                    "表示名": "ステージ",
                    "対応フィールドAPI名": "StageName",
                    "型": "picklist",
                    "備考": "",
                },
            ],
        )
        site = fake_site(describe_response, fields_table)
        with patch("tools.dump_soql_drafts.site_for", return_value=site):
            dump_soql_drafts(master, output)
        rows = _read_rows(output)
        raw = rows[0]["フィルタ詳細(生データ)"]
        assert "STAGE=equals:Closed Won" in raw
        assert "TYPE=includes:['A', 'B']" in raw

    def test_raw_filters_are_present_even_for_unsupported_format(self, tmp_path):
        """SUMMARY/MATRIXでSOQLドラフトが作れなくても、生データ列は出ること。"""
        master = _master_with_one_report(tmp_path)
        output = tmp_path / "out.csv"
        describe_response = {
            "reportMetadata": {
                "reportFormat": "SUMMARY",
                "reportFilters": [
                    {"column": "STAGE", "operator": "equals", "value": "Closed Won"},
                ],
            }
        }
        site = fake_site(describe_response)
        with patch("tools.dump_soql_drafts.site_for", return_value=site):
            dump_soql_drafts(master, output)
        rows = _read_rows(output)
        assert rows[0]["SOQLドラフト"] == ""
        assert "STAGE=equals:Closed Won" in rows[0]["フィルタ詳細(生データ)"]

    def test_no_filters_produces_empty_raw_details(self, tmp_path):
        master = _master_with_one_report(tmp_path)
        output = tmp_path / "out.csv"
        describe_response = {
            "reportMetadata": {
                "reportFormat": "TABULAR",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPP_NAME"],
                "reportFilters": [],
            }
        }
        fields_table = Table(
            FIELDS_COLUMNS,
            [
                {
                    "列キー": "OPP_NAME",
                    "表示名": "案件名",
                    "対応フィールドAPI名": "Name",
                    "型": "string",
                    "備考": "",
                },
            ],
        )
        site = fake_site(describe_response, fields_table)
        with patch("tools.dump_soql_drafts.site_for", return_value=site):
            dump_soql_drafts(master, output)
        rows = _read_rows(output)
        assert rows[0]["フィルタ詳細(生データ)"] == ""

    def test_unexpected_report_filters_shape_does_not_break(self, tmp_path):
        """``reportFilters`` が dict 以外の要素を含んでいてもスキップせず処理を続ける。"""
        master = _master_with_one_report(tmp_path)
        output = tmp_path / "out.csv"
        describe_response = {
            "reportMetadata": {
                "reportFormat": "TABULAR",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPP_NAME"],
                "reportFilters": ["unexpected"],
            }
        }
        fields_table = Table(
            FIELDS_COLUMNS,
            [
                {
                    "列キー": "OPP_NAME",
                    "表示名": "案件名",
                    "対応フィールドAPI名": "Name",
                    "型": "string",
                    "備考": "",
                },
            ],
        )
        site = fake_site(describe_response, fields_table)
        with patch("tools.dump_soql_drafts.site_for", return_value=site):
            dump_soql_drafts(master, output)
        rows = _read_rows(output)
        assert rows[0]["フィルタ詳細(生データ)"] == "(不正な要素)"


class TestUnresolvedFields:
    def test_unresolved_select_column_is_excluded_and_noted(self, tmp_path):
        master = _master_with_one_report(tmp_path)
        output = tmp_path / "out.csv"
        describe_response = {
            "reportMetadata": {
                "reportFormat": "TABULAR",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPP_NAME", "MYSTERY_COLUMN"],
                "reportFilters": [],
            }
        }
        fields_table = Table(
            FIELDS_COLUMNS,
            [
                {
                    "列キー": "OPP_NAME",
                    "表示名": "案件名",
                    "対応フィールドAPI名": "Name",
                    "型": "string",
                    "備考": "",
                },
                {
                    "列キー": "MYSTERY_COLUMN",
                    "表示名": "謎の列",
                    "対応フィールドAPI名": "(不明)",
                    "型": "",
                    "備考": "対応フィールドなし",
                },
            ],
        )
        site = fake_site(describe_response, fields_table)
        with patch("tools.dump_soql_drafts.site_for", return_value=site):
            dump_soql_drafts(master, output)
        rows = _read_rows(output)
        assert rows[0]["SOQLドラフト"] == "SELECT Name FROM Opportunity"
        assert rows[0]["状態"] == "REVIEW"
        assert "MYSTERY_COLUMN" in rows[0]["備考"]

    def test_all_columns_unresolved_falls_back_to_id(self, tmp_path):
        master = _master_with_one_report(tmp_path)
        output = tmp_path / "out.csv"
        describe_response = {
            "reportMetadata": {
                "reportFormat": "TABULAR",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["MYSTERY_COLUMN"],
                "reportFilters": [],
            }
        }
        fields_table = Table(
            FIELDS_COLUMNS,
            [
                {
                    "列キー": "MYSTERY_COLUMN",
                    "表示名": "謎の列",
                    "対応フィールドAPI名": "(不明)",
                    "型": "",
                    "備考": "対応フィールドなし",
                },
            ],
        )
        site = fake_site(describe_response, fields_table)
        with patch("tools.dump_soql_drafts.site_for", return_value=site):
            dump_soql_drafts(master, output)
        rows = _read_rows(output)
        assert rows[0]["SOQLドラフト"] == "SELECT Id FROM Opportunity"
        assert "Id" in rows[0]["備考"]

    def test_unresolved_filter_column_is_excluded_from_where(self, tmp_path):
        master = _master_with_one_report(tmp_path)
        output = tmp_path / "out.csv"
        describe_response = {
            "reportMetadata": {
                "reportFormat": "TABULAR",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPP_NAME"],
                "reportFilters": [
                    {"column": "MYSTERY_COLUMN", "operator": "equals", "value": "x"},
                ],
            }
        }
        fields_table = Table(
            FIELDS_COLUMNS,
            [
                {
                    "列キー": "OPP_NAME",
                    "表示名": "案件名",
                    "対応フィールドAPI名": "Name",
                    "型": "string",
                    "備考": "",
                },
            ],
        )
        site = fake_site(describe_response, fields_table)
        with patch("tools.dump_soql_drafts.site_for", return_value=site):
            dump_soql_drafts(master, output)
        rows = _read_rows(output)
        assert rows[0]["SOQLドラフト"] == ""
        assert rows[0]["状態"] == "BLOCKED"
        assert "MYSTERY_COLUMN" in rows[0]["備考"]


class TestManualOperators:
    def test_includes_operator_is_excluded_from_where_and_noted(self, tmp_path):
        master = _master_with_one_report(tmp_path)
        output = tmp_path / "out.csv"
        describe_response = {
            "reportMetadata": {
                "reportFormat": "TABULAR",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPP_NAME"],
                "reportFilters": [
                    {"column": "STAGE", "operator": "includes", "value": "A;B"},
                ],
            }
        }
        fields_table = Table(
            FIELDS_COLUMNS,
            [
                {
                    "列キー": "OPP_NAME",
                    "表示名": "案件名",
                    "対応フィールドAPI名": "Name",
                    "型": "string",
                    "備考": "",
                },
                {
                    "列キー": "STAGE",
                    "表示名": "ステージ",
                    "対応フィールドAPI名": "StageName",
                    "型": "picklist",
                    "備考": "",
                },
            ],
        )
        site = fake_site(describe_response, fields_table)
        with patch("tools.dump_soql_drafts.site_for", return_value=site):
            dump_soql_drafts(master, output)
        rows = _read_rows(output)
        assert rows[0]["SOQLドラフト"] == ""
        assert rows[0]["状態"] == "BLOCKED"
        assert "includes" in rows[0]["備考"]


class TestStandardDateFilter:
    def test_custom_range_is_converted(self, tmp_path):
        master = _master_with_one_report(tmp_path)
        output = tmp_path / "out.csv"
        describe_response = {
            "reportMetadata": {
                "reportFormat": "TABULAR",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPP_NAME"],
                "reportFilters": [],
                "standardDateFilter": {
                    "column": "CloseDate",
                    "durationValue": "CUSTOM",
                    "startDate": "2024-01-01",
                    "endDate": "2024-12-31",
                },
            }
        }
        fields_table = Table(
            FIELDS_COLUMNS,
            [
                {
                    "列キー": "OPP_NAME",
                    "表示名": "案件名",
                    "対応フィールドAPI名": "Name",
                    "型": "string",
                    "備考": "",
                },
            ],
        )
        site = fake_site(describe_response, fields_table)
        with patch("tools.dump_soql_drafts.site_for", return_value=site):
            dump_soql_drafts(master, output)
        rows = _read_rows(output)
        assert rows[0]["SOQLドラフト"] == (
            "SELECT Name FROM Opportunity WHERE CloseDate >= 2024-01-01 AND CloseDate <= 2024-12-31"
        )

    def test_named_duration_is_excluded_and_noted(self, tmp_path):
        """``THIS_MONTH`` のような相対期間は機械変換せず備考へ回す。"""
        master = _master_with_one_report(tmp_path)
        output = tmp_path / "out.csv"
        describe_response = {
            "reportMetadata": {
                "reportFormat": "TABULAR",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPP_NAME"],
                "reportFilters": [],
                "standardDateFilter": {
                    "column": "CloseDate",
                    "durationValue": "THIS_MONTH",
                },
            }
        }
        fields_table = Table(
            FIELDS_COLUMNS,
            [
                {
                    "列キー": "OPP_NAME",
                    "表示名": "案件名",
                    "対応フィールドAPI名": "Name",
                    "型": "string",
                    "備考": "",
                },
            ],
        )
        site = fake_site(describe_response, fields_table)
        with patch("tools.dump_soql_drafts.site_for", return_value=site):
            dump_soql_drafts(master, output)
        rows = _read_rows(output)
        assert rows[0]["SOQLドラフト"] == ""
        assert rows[0]["状態"] == "BLOCKED"
        assert "THIS_MONTH" in rows[0]["備考"]


class TestCrossFilters:
    def test_cross_filters_are_noted_but_not_converted(self, tmp_path):
        master = _master_with_one_report(tmp_path)
        output = tmp_path / "out.csv"
        describe_response = {
            "reportMetadata": {
                "reportFormat": "TABULAR",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPP_NAME"],
                "reportFilters": [],
                "crossFilters": [{"relatedEntity": "OpportunityLineItem"}],
            }
        }
        fields_table = Table(
            FIELDS_COLUMNS,
            [
                {
                    "列キー": "OPP_NAME",
                    "表示名": "案件名",
                    "対応フィールドAPI名": "Name",
                    "型": "string",
                    "備考": "",
                },
            ],
        )
        site = fake_site(describe_response, fields_table)
        with patch("tools.dump_soql_drafts.site_for", return_value=site):
            dump_soql_drafts(master, output)
        rows = _read_rows(output)
        assert rows[0]["SOQLドラフト"] == ""
        assert rows[0]["状態"] == "BLOCKED"
        assert "crossFilters" in rows[0]["備考"]

    def test_cross_filters_raw_data_appears_in_filter_detail_column(self, tmp_path):
        """crossFiltersの生データは「フィルタ詳細(生データ)」列で確認できる。"""
        master = _master_with_one_report(tmp_path)
        output = tmp_path / "out.csv"
        describe_response = {
            "reportMetadata": {
                "reportFormat": "TABULAR",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPP_NAME"],
                "reportFilters": [
                    {"column": "STAGE", "operator": "equals", "value": "Closed Won"},
                ],
                "crossFilters": [{"relatedEntity": "OpportunityLineItem", "operator": "with"}],
            }
        }
        fields_table = Table(
            FIELDS_COLUMNS,
            [
                {
                    "列キー": "OPP_NAME",
                    "表示名": "案件名",
                    "対応フィールドAPI名": "Name",
                    "型": "string",
                    "備考": "",
                },
                {
                    "列キー": "STAGE",
                    "表示名": "ステージ",
                    "対応フィールドAPI名": "StageName",
                    "型": "picklist",
                    "備考": "",
                },
            ],
        )
        site = fake_site(describe_response, fields_table)
        with patch("tools.dump_soql_drafts.site_for", return_value=site):
            dump_soql_drafts(master, output)
        rows = _read_rows(output)
        detail = rows[0]["フィルタ詳細(生データ)"]
        # reportFilters の生データと crossFilters の生データが両方残る
        assert "STAGE=equals:Closed Won" in detail
        assert "crossFilters:" in detail
        assert "OpportunityLineItem" in detail
        assert "with" in detail

    def test_cross_filters_raw_data_alone_when_no_report_filters(self, tmp_path):
        """reportFiltersが無くcrossFiltersだけのときも生データが残る。"""
        master = _master_with_one_report(tmp_path)
        output = tmp_path / "out.csv"
        describe_response = {
            "reportMetadata": {
                "reportFormat": "TABULAR",
                "reportFilters": [],
                "crossFilters": [{"relatedEntity": "Contact"}],
            }
        }
        site = fake_site(describe_response)
        with patch("tools.dump_soql_drafts.site_for", return_value=site):
            dump_soql_drafts(master, output)
        rows = _read_rows(output)
        assert rows[0]["フィルタ詳細(生データ)"] == "crossFilters: relatedEntity=Contact"


class TestBooleanFilter:
    def test_expands_and_or_parentheses_and_not(self):
        conditions = {1: "A = 1", 2: "B = 2", 3: "C = 3"}

        expanded = _expand_boolean_filter("1 AND (2 OR NOT 3)", conditions)

        assert expanded == "(A = 1) AND ((B = 2) OR NOT ((C = 3)))"

    def test_returns_none_when_expression_references_unresolved_condition(self):
        assert _expand_boolean_filter("1 OR 2", {1: "A = 1"}) is None

    def test_returns_none_for_invalid_syntax(self):
        assert _expand_boolean_filter("1 AND OR 2", {1: "A = 1", 2: "B = 2"}) is None


class TestCatalogMerge:
    def test_confirmed_mapping_is_not_overwritten(self):
        confirmed = {
            "サイトクラス": "Site",
            "レポートタイプ": "Opportunity",
            "列キー": "CUSTOM",
            "表示名": "独自列",
            "フィールドAPI名": "Confirmed__c",
            "型": "string",
            "確認状態": "確認済み",
            "備考": "手動確認",
        }
        observed = {**confirmed, "フィールドAPI名": "Other__c", "確認状態": "未確認"}

        assert _merge_catalog_rows([confirmed], [observed]) == [confirmed]

    def test_conflicting_automatic_candidates_require_review(self):
        first = {
            "サイトクラス": "Site",
            "レポートタイプ": "Opportunity",
            "列キー": "CUSTOM",
            "表示名": "独自列",
            "フィールドAPI名": "First__c",
            "型": "string",
            "確認状態": "未確認",
            "備考": "",
        }
        second = {**first, "フィールドAPI名": "Second__c"}

        merged = _merge_catalog_rows([first], [second])

        assert merged[0]["確認状態"] == "要確認"
        assert merged[0]["フィールドAPI名"] == "(不明)"
        assert "First__c" in merged[0]["備考"]
        assert "Second__c" in merged[0]["備考"]


class TestTypedLiteral:
    def test_numeric_looking_id_is_quoted(self):
        assert _filter_to_condition("ExternalId__c", "id", "equals", "00123") == (
            "ExternalId__c = '00123'"
        )

    def test_boolean_and_date_are_not_quoted(self):
        assert _filter_to_condition("Active__c", "boolean", "equals", "TRUE") == (
            "Active__c = true"
        )
        assert _filter_to_condition("CloseDate", "date", "equals", "2026-09-09") == (
            "CloseDate = 2026-09-09"
        )

    def test_invalid_typed_value_is_unresolved(self):
        assert _filter_to_condition("Amount", "currency", "equals", "one") is None


class TestSoqlValidation:
    """``VALIDATE_SOQL`` を有効化したときの実行時検証。"""

    def _ready_describe_response(self):
        return {
            "reportMetadata": {
                "reportFormat": "TABULAR",
                "reportType": {"type": "Opportunity"},
                "detailColumns": ["OPP_NAME"],
                "reportFilters": [],
            }
        }

    def _ready_fields_table(self):
        return Table(
            FIELDS_COLUMNS,
            [
                {
                    "列キー": "OPP_NAME",
                    "表示名": "案件名",
                    "対応フィールドAPI名": "Name",
                    "型": "string",
                    "備考": "",
                },
            ],
        )

    def test_disabled_by_default_does_not_call_query_rows(self, tmp_path):
        """既定(VALIDATE_SOQL=False)では query_rows() を一切呼ばない(API呼び出しを増やさない)。"""
        master = _master_with_one_report(tmp_path)
        output = tmp_path / "out.csv"
        site = fake_site(self._ready_describe_response(), self._ready_fields_table())
        with patch("tools.dump_soql_drafts.site_for", return_value=site):
            dump_soql_drafts(master, output)
        salesforce_client = site.return_value.__enter__.return_value
        salesforce_client.query_rows.assert_not_called()
        assert _read_rows(output)[0]["状態"] == "READY"

    def test_enabled_marks_invalid_on_query_failure(self, tmp_path, monkeypatch):
        """有効化時、query_rows()がSalesforceRequestErrorを出したらINVALIDに落とす。"""
        import tools.dump_soql_drafts as module
        from comken.exceptions import SalesforceRequestError

        monkeypatch.setattr(module, "VALIDATE_SOQL", True)
        master = _master_with_one_report(tmp_path)
        output = tmp_path / "out.csv"
        site = fake_site(self._ready_describe_response(), self._ready_fields_table())
        salesforce_client = site.return_value.__enter__.return_value
        salesforce_client.query_rows.side_effect = SalesforceRequestError(
            "GET", "/query", 400, "MALFORMED_QUERY: 項目名が不正です"
        )
        with patch("tools.dump_soql_drafts.site_for", return_value=site):
            dump_soql_drafts(master, output)
        row = _read_rows(output)[0]
        assert row["状態"] == "INVALID"
        assert "SOQL検証失敗" in row["備考"]
        assert "MALFORMED_QUERY" in row["備考"]

    def test_enabled_keeps_ready_on_query_success(self, tmp_path, monkeypatch):
        """有効化時、query_rows()が成功すればREADYのまま。"""
        import tools.dump_soql_drafts as module

        monkeypatch.setattr(module, "VALIDATE_SOQL", True)
        master = _master_with_one_report(tmp_path)
        output = tmp_path / "out.csv"
        site = fake_site(self._ready_describe_response(), self._ready_fields_table())
        salesforce_client = site.return_value.__enter__.return_value
        salesforce_client.query_rows.return_value = iter([])
        with patch("tools.dump_soql_drafts.site_for", return_value=site):
            dump_soql_drafts(master, output)
        assert _read_rows(output)[0]["状態"] == "READY"

    def test_enabled_appends_limit_to_soql_without_one(self, tmp_path, monkeypatch):
        """既にLIMIT句が無いドラフトへはLIMIT 1を付けて検証する。"""
        import tools.dump_soql_drafts as module

        monkeypatch.setattr(module, "VALIDATE_SOQL", True)
        master = _master_with_one_report(tmp_path)
        output = tmp_path / "out.csv"
        site = fake_site(self._ready_describe_response(), self._ready_fields_table())
        salesforce_client = site.return_value.__enter__.return_value
        salesforce_client.query_rows.return_value = iter([])
        with patch("tools.dump_soql_drafts.site_for", return_value=site):
            dump_soql_drafts(master, output)
        called_soql = salesforce_client.query_rows.call_args[0][0]
        assert called_soql == "SELECT Name FROM Opportunity LIMIT 1"

    def test_enabled_skips_non_ready_drafts(self, tmp_path, monkeypatch):
        """BLOCKEDなど非READYのドラフトは検証しない(不完全なSOQLを実行しない)。"""
        import tools.dump_soql_drafts as module

        monkeypatch.setattr(module, "VALIDATE_SOQL", True)
        master = _master_with_one_report(tmp_path)
        output = tmp_path / "out.csv"
        describe_response = {"reportMetadata": {"reportFormat": "SUMMARY"}}
        site = fake_site(describe_response)
        with patch("tools.dump_soql_drafts.site_for", return_value=site):
            dump_soql_drafts(master, output)
        salesforce_client = site.return_value.__enter__.return_value
        salesforce_client.query_rows.assert_not_called()
        assert _read_rows(output)[0]["状態"] == "BLOCKED"


class TestFailureHandling:
    def test_describe_failure_does_not_stop_others(self, tmp_path):
        master = make_master(
            tmp_path / "管理表.xlsx",
            [
                ["1001", "営業事務グループ", "山田", "落ちる方", URL_A, str(tmp_path), "○", ""],
                ["1002", "経理グループ", "佐藤", "通る方", URL_B, str(tmp_path), "○", ""],
            ],
        )
        output = tmp_path / "out.csv"

        def _describe_by_report_id(report_id: str) -> dict:
            if report_id == "00O5g00000ABCDE":
                raise RuntimeError("アクセス権限がありません")
            return {
                "reportMetadata": {
                    "reportFormat": "TABULAR",
                    "reportType": {"type": "Opportunity"},
                    "detailColumns": ["OPP_NAME"],
                    "reportFilters": [],
                }
            }

        site_a = MagicMock()
        client_a = MagicMock()
        client_a.__enter__.return_value.report.describe.side_effect = _describe_by_report_id
        site_a.return_value = client_a
        site_a.__name__ = "FakeSiteA"
        site_a.DISPLAY_NAME = "テスト組織A"

        fields_table = Table(
            FIELDS_COLUMNS,
            [
                {
                    "列キー": "OPP_NAME",
                    "表示名": "案件名",
                    "対応フィールドAPI名": "Name",
                    "型": "string",
                    "備考": "",
                },
            ],
        )
        site_b = fake_site(
            {
                "reportMetadata": {
                    "reportFormat": "TABULAR",
                    "reportType": {"type": "Opportunity"},
                    "detailColumns": ["OPP_NAME"],
                    "reportFilters": [],
                }
            },
            fields_table,
        )
        site_b.__name__ = "FakeSiteB"
        site_b.DISPLAY_NAME = "テスト組織B"

        site_for_results = {URL_A: site_a, URL_B: site_b}

        def fake_site_for(url: str) -> MagicMock:
            return site_for_results[url]

        with patch("tools.dump_soql_drafts.site_for", side_effect=fake_site_for):
            written = dump_soql_drafts(master, output)
        assert written == 2
        by_key = {row["管理番号"]: row for row in _read_rows(output)}
        assert by_key["1001"]["SOQLドラフト"] == ""
        assert by_key["1001"]["備考"].startswith(FAILED_PREFIX)
        assert by_key["1002"]["備考"] == ""


class TestMasterLoading:
    def test_output_path_constant_is_the_expected_default(self):
        """出力先はCLI引数ではなく OUTPUT_PATH を直接書き換える運用。"""
        from tools.dump_soql_drafts import OUTPUT_PATH

        assert Path("soql_drafts_dump.csv") == OUTPUT_PATH

    def test_empty_master_produces_header_only_csv(self, tmp_path):
        master = make_master(tmp_path / "管理表.xlsx", [])
        output = tmp_path / "out.csv"
        from tools import dump_soql_drafts as module

        with (
            patch.object(module, "load_master", return_value={}),
            patch.object(module, "_group_entries_by_site", return_value=[]),
        ):
            written = dump_soql_drafts(master, output)
        assert written == 0
        rows = _read_rows(output)
        assert rows == []
