"""``tools/dump_soql_drafts.py`` のテスト。

Salesforce には繋がず、管理表は ``tmp_path`` 配下に作って実物を読み込ませ、
``site_for()``（``tools.dump_report_filters`` 経由で参照される）は
``unittest.mock.patch`` で差し替える。
"""

import csv
from pathlib import Path
from unittest.mock import MagicMock, patch

from comken.core.table import Table
from comken.toolbox.excel import Excel
from tools.dump_soql_drafts import CSV_HEADERS, FAILED_PREFIX, dump_soql_drafts

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
    report.describe_fields.return_value = fields_table or Table(FIELDS_COLUMNS, [])
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
        with patch("tools.dump_report_filters.site_for", return_value=site):
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
        with patch("tools.dump_report_filters.site_for", return_value=site):
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
        with patch("tools.dump_report_filters.site_for", return_value=site):
            dump_soql_drafts(master, output)
        rows = _read_rows(output)
        assert rows[0]["SOQLドラフト"] == "SELECT Name FROM Opportunity"


class TestUnsupportedReportFormat:
    def test_summary_format_is_excluded_with_note(self, tmp_path):
        master = _master_with_one_report(tmp_path)
        output = tmp_path / "out.csv"
        describe_response = {"reportMetadata": {"reportFormat": "SUMMARY"}}
        site = fake_site(describe_response)
        with patch("tools.dump_report_filters.site_for", return_value=site):
            dump_soql_drafts(master, output)
        rows = _read_rows(output)
        assert rows[0]["SOQLドラフト"] == ""
        assert "SUMMARY" in rows[0]["備考"] or "対象外" in rows[0]["備考"]

    def test_matrix_format_is_excluded_with_note(self, tmp_path):
        master = _master_with_one_report(tmp_path)
        output = tmp_path / "out.csv"
        describe_response = {"reportMetadata": {"reportFormat": "MATRIX"}}
        site = fake_site(describe_response)
        with patch("tools.dump_report_filters.site_for", return_value=site):
            dump_soql_drafts(master, output)
        rows = _read_rows(output)
        assert rows[0]["SOQLドラフト"] == ""
        assert "対象外" in rows[0]["備考"]


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
        with patch("tools.dump_report_filters.site_for", return_value=site):
            dump_soql_drafts(master, output)
        rows = _read_rows(output)
        assert rows[0]["SOQLドラフト"] == "SELECT Name FROM Opportunity"
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
        with patch("tools.dump_report_filters.site_for", return_value=site):
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
        with patch("tools.dump_report_filters.site_for", return_value=site):
            dump_soql_drafts(master, output)
        rows = _read_rows(output)
        assert rows[0]["SOQLドラフト"] == "SELECT Name FROM Opportunity"
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
        with patch("tools.dump_report_filters.site_for", return_value=site):
            dump_soql_drafts(master, output)
        rows = _read_rows(output)
        assert rows[0]["SOQLドラフト"] == "SELECT Name FROM Opportunity"
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
        with patch("tools.dump_report_filters.site_for", return_value=site):
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
        with patch("tools.dump_report_filters.site_for", return_value=site):
            dump_soql_drafts(master, output)
        rows = _read_rows(output)
        assert rows[0]["SOQLドラフト"] == "SELECT Name FROM Opportunity"
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
        with patch("tools.dump_report_filters.site_for", return_value=site):
            dump_soql_drafts(master, output)
        rows = _read_rows(output)
        assert rows[0]["SOQLドラフト"] == "SELECT Name FROM Opportunity"
        assert "crossFilters" in rows[0]["備考"]


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

        with patch("tools.dump_report_filters.site_for", side_effect=fake_site_for):
            written = dump_soql_drafts(master, output)
        assert written == 2
        by_key = {row["管理番号"]: row for row in _read_rows(output)}
        assert by_key["1001"]["SOQLドラフト"] == ""
        assert by_key["1001"]["備考"].startswith(FAILED_PREFIX)
        assert by_key["1002"]["備考"] == ""


class TestMasterLoading:
    def test_default_output_path_is_used_when_not_specified(self):
        from tools.dump_soql_drafts import DEFAULT_OUTPUT_PATH

        assert Path("soql_drafts_dump.csv") == DEFAULT_OUTPUT_PATH

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
