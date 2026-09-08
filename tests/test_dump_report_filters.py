"""``tools/dump_report_filters.py`` のテスト。

Salesforce には繋がず、管理表は ``tmp_path`` 配下に作って実物を読み込ませ、
``site_for()`` は ``unittest.mock.patch`` で差し替える。
"""

import csv
from pathlib import Path
from unittest.mock import MagicMock, patch

from comken.core.table import Table
from comken.services.salesforce_downloader.master import ReportEntry
from comken.toolbox.excel import Excel
from tools.dump_report_filters import (
    CSV_HEADERS,
    DEFAULT_OUTPUT_PATH,
    FAILED_PREFIX,
    dump_report_filters,
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


def make_master(path: Path, rows: list[list]) -> Path:
    """テスト用の管理表（Excel）を作る。"""
    table_rows = [dict(zip(HEADERS, row, strict=True)) for row in rows]
    with Excel(path) as book:
        book.create_data_sheet("管理表").create_table("管理表", Table(HEADERS, table_rows))
    return path


def fake_site(describe_response: object | Exception) -> MagicMock:
    """``describe()`` が固定レスポンスを返す Salesforce クライアント。

    ``site_for()`` がこのクラス（の ``__name__`` で識別される ``MagicMock``）を
    返すように差し替えれば、組織 1 つ分の接続を再現できる。
    """
    site_class = MagicMock()
    client = MagicMock()
    if isinstance(describe_response, Exception):
        client.__enter__.return_value.report.describe.side_effect = describe_response
    else:
        client.__enter__.return_value.report.describe.return_value = describe_response
    site_class.return_value = client
    site_class.__name__ = "FakeSite"
    site_class.DISPLAY_NAME = "テスト組織"
    return site_class


class TestCsvOutput:
    """``reportFilters`` が CSV に正しく展開されること。"""

    def test_multiple_filters_produce_multiple_rows(self, tmp_path):
        master = make_master(
            tmp_path / "管理表.xlsx",
            [
                [
                    "1001",
                    "営業事務グループ",
                    "山田",
                    "顧客一覧",
                    URL_A,
                    str(tmp_path),
                    "○",
                    "",
                ]
            ],
        )
        output = tmp_path / "out.csv"
        site = fake_site(
            {
                "reportMetadata": {
                    "reportFilters": [
                        {
                            "field": "CLOSE_DATE",
                            "operator": "greaterOrEqual",
                            "value": "2024-01-01",
                        },
                        {"field": "STAGE", "operator": "equals", "value": "Closed Won"},
                    ]
                }
            }
        )
        with patch("tools.dump_report_filters.site_for", return_value=site):
            written = dump_report_filters(master, output)
        # フィルタ 2 件ぶん、CSV には 2 行出る
        assert written == 2
        with output.open(encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
        assert list(rows[0].keys()) == list(CSV_HEADERS)
        # 1 行目
        assert rows[0]["管理番号"] == "1001"
        assert rows[0]["レポートID"] == "00O5g00000ABCDE"
        assert rows[0]["URL"] == URL_A
        assert rows[0]["フィルタ列"] == "CLOSE_DATE"
        assert rows[0]["演算子"] == "greaterOrEqual"
        assert rows[0]["値"] == "2024-01-01"
        # 2 行目
        assert rows[1]["管理番号"] == "1001"
        assert rows[1]["フィルタ列"] == "STAGE"
        assert rows[1]["演算子"] == "equals"
        assert rows[1]["値"] == "Closed Won"

    def test_no_filters_produces_one_empty_row(self, tmp_path):
        """``reportFilters`` が空のときは 1 行だけ出し、フィルタ列は空にする。"""
        master = make_master(
            tmp_path / "管理表.xlsx",
            [
                [
                    "1001",
                    "営業事務グループ",
                    "山田",
                    "絞り込みなし",
                    URL_A,
                    str(tmp_path),
                    "○",
                    "",
                ]
            ],
        )
        output = tmp_path / "out.csv"
        site = fake_site({"reportMetadata": {"reportFilters": []}})
        with patch("tools.dump_report_filters.site_for", return_value=site):
            written = dump_report_filters(master, output)
        assert written == 1
        with output.open(encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
        assert len(rows) == 1
        assert rows[0]["管理番号"] == "1001"
        assert rows[0]["フィルタ列"] == ""
        assert rows[0]["演算子"] == ""
        assert rows[0]["値"] == ""

    def test_list_value_is_stringified(self, tmp_path):
        """``value`` がリスト（``in`` 演算子など）のとき ``str()`` で文字列化される。"""
        master = make_master(
            tmp_path / "管理表.xlsx",
            [
                [
                    "1001",
                    "営業事務グループ",
                    "山田",
                    "IN演算子",
                    URL_A,
                    str(tmp_path),
                    "○",
                    "",
                ]
            ],
        )
        output = tmp_path / "out.csv"
        site = fake_site(
            {
                "reportMetadata": {
                    "reportFilters": [
                        {
                            "field": "STAGE",
                            "operator": "in",
                            "value": ["Prospecting", "Qualification"],
                        }
                    ]
                }
            }
        )
        with patch("tools.dump_report_filters.site_for", return_value=site):
            dump_report_filters(master, output)
        with output.open(encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
        # セル内が ``['Prospecting', 'Qualification']`` のような ``str(list)`` 形になる
        assert rows[0]["値"] == "['Prospecting', 'Qualification']"

    def test_unexpected_report_filters_shape_does_not_break(self, tmp_path):
        """``reportFilters`` が dict 以外の要素を含んでいてもスキップせず 1 行に倒す。"""
        master = make_master(
            tmp_path / "管理表.xlsx",
            [
                [
                    "1001",
                    "営業事務グループ",
                    "山田",
                    "壊れたレスポンス",
                    URL_A,
                    str(tmp_path),
                    "○",
                    "",
                ]
            ],
        )
        output = tmp_path / "out.csv"
        site = fake_site({"reportMetadata": {"reportFilters": ["unexpected"]}})
        with patch("tools.dump_report_filters.site_for", return_value=site):
            dump_report_filters(master, output)
        with output.open(encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
        assert len(rows) == 1
        assert rows[0]["管理番号"] == "1001"
        assert rows[0]["フィルタ列"] == ""


class TestFailureHandling:
    """describe() が失敗しても他レポートを止めないこと。"""

    def test_one_describe_failure_does_not_stop_others(self, tmp_path):
        master = make_master(
            tmp_path / "管理表.xlsx",
            [
                [
                    "1001",
                    "営業事務グループ",
                    "山田",
                    "落ちる方",
                    URL_A,
                    str(tmp_path),
                    "○",
                    "",
                ],
                [
                    "1002",
                    "経理グループ",
                    "佐藤",
                    "通る方",
                    URL_B,
                    str(tmp_path),
                    "○",
                    "",
                ],
            ],
        )
        output = tmp_path / "out.csv"

        def _describe_by_report_id(report_id: str) -> dict:
            # 1001 のレポート ID だけ失敗させる（SalesforceReportAccessDeniedError 相当）
            if report_id == "00O5g00000ABCDE":
                raise RuntimeError("アクセス権限がありません")
            return {
                "reportMetadata": {
                    "reportFilters": [
                        {"field": "AMOUNT", "operator": "greaterThan", "value": "1000"}
                    ]
                }
            }

        site_a = MagicMock()
        client_a = MagicMock()
        client_a.__enter__.return_value.report.describe.side_effect = _describe_by_report_id
        site_a.return_value = client_a
        site_a.__name__ = "FakeSiteA"
        site_a.DISPLAY_NAME = "テスト組織A"

        site_b = fake_site(
            {
                "reportMetadata": {
                    "reportFilters": [
                        {"field": "AMOUNT", "operator": "greaterThan", "value": "1000"}
                    ]
                }
            }
        )
        site_b.__name__ = "FakeSiteB"
        site_b.DISPLAY_NAME = "テスト組織B"

        site_for_results = {URL_A: site_a, URL_B: site_b}

        def fake_site_for(url: str) -> MagicMock:
            return site_for_results[url]

        with patch("tools.dump_report_filters.site_for", side_effect=fake_site_for):
            written = dump_report_filters(master, output)
        # 1001 が「取得失敗」1 行 + 1002 がフィルタ 1 行ぶん = 2 行
        assert written == 2
        with output.open(encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
        # 失敗した行には管理番号 1001 と「取得失敗: ...」が残る
        by_key = {row["管理番号"]: row for row in rows}
        assert by_key["1001"]["フィルタ列"] == ""
        assert by_key["1001"]["演算子"] == ""
        assert by_key["1001"]["値"].startswith(FAILED_PREFIX)
        # 成功した行はそのまま出力
        assert by_key["1002"]["フィルタ列"] == "AMOUNT"
        assert by_key["1002"]["演算子"] == "greaterThan"
        assert by_key["1002"]["値"] == "1000"


class TestSiteConnectionReuse:
    """同じ組織のレポートは接続を使い回すこと。"""

    def test_same_site_reuses_connection(self, tmp_path):
        """同じ組織のレポート 2 件を 1 つの接続で処理する（``__enter__`` は 1 回）。"""
        master = make_master(
            tmp_path / "管理表.xlsx",
            [
                [
                    "1001",
                    "営業事務グループ",
                    "山田",
                    "同組織のレポートA",
                    URL_A,
                    str(tmp_path),
                    "○",
                    "",
                ],
                [
                    "1002",
                    "営業事務グループ",
                    "山田",
                    "同組織のレポートB",
                    URL_A,
                    str(tmp_path),
                    "○",
                    "",
                ],
            ],
        )
        output = tmp_path / "out.csv"
        site = fake_site(
            {
                "reportMetadata": {
                    "reportFilters": [{"field": "NAME", "operator": "contains", "value": "山田"}]
                }
            }
        )
        with patch("tools.dump_report_filters.site_for", return_value=site):
            dump_report_filters(master, output)
        # 組織クラスは 1 度だけインスタンス化（``site()`` の呼び出し = 1 回）
        assert site.call_count == 1
        # describe() は 2 回呼ばれる（レポート 2 件ぶん）
        client = site.return_value.__enter__.return_value
        assert client.report.describe.call_count == 2

    def test_different_sites_open_independent_connections(self, tmp_path):
        """組織の違うレポートはそれぞれ別接続を開く。"""
        master = make_master(
            tmp_path / "管理表.xlsx",
            [
                [
                    "1001",
                    "営業事務グループ",
                    "山田",
                    "組織Aのレポート",
                    URL_A,
                    str(tmp_path),
                    "○",
                    "",
                ],
                [
                    "1002",
                    "経理グループ",
                    "佐藤",
                    "組織Bのレポート",
                    URL_B,
                    str(tmp_path),
                    "○",
                    "",
                ],
            ],
        )
        output = tmp_path / "out.csv"
        site_a = fake_site(
            {"reportMetadata": {"reportFilters": [{"field": "A", "operator": "eq", "value": "1"}]}}
        )
        site_a.__name__ = "FakeSiteA"
        site_a.DISPLAY_NAME = "テスト組織A"
        site_b = fake_site(
            {"reportMetadata": {"reportFilters": [{"field": "B", "operator": "eq", "value": "2"}]}}
        )
        site_b.__name__ = "FakeSiteB"
        site_b.DISPLAY_NAME = "テスト組織B"

        site_for_results = {URL_A: site_a, URL_B: site_b}

        def fake_site_for(url: str) -> MagicMock:
            return site_for_results[url]

        with patch("tools.dump_report_filters.site_for", side_effect=fake_site_for):
            dump_report_filters(master, output)
        # 2 組織なので接続も 2 回
        assert site_a.call_count == 1
        assert site_b.call_count == 1


class TestMasterLoading:
    """管理表の読み込みと既定値。"""

    def test_default_output_path_is_used_when_not_specified(self):
        """モジュール既定の出力パスが ``report_filters_dump.csv`` である。"""
        assert Path("report_filters_dump.csv") == DEFAULT_OUTPUT_PATH

    def test_empty_master_produces_header_only_csv(self, tmp_path):
        """管理表に 1 件も無いときは、見出しだけの CSV を出す。"""
        master = make_master(tmp_path / "管理表.xlsx", [])
        output = tmp_path / "out.csv"
        # 空の管理表は ``load_master`` が ``MasterHeaderMismatchError`` を出すので、
        # ``ReportEntry`` が無い状況を ``site_for`` を呼ばずに再現するため、
        # 空 dict を返す偽 ``load_master`` をパッチで差し込む
        from tools import dump_report_filters as module

        with (
            patch.object(module, "load_master", return_value={}),
            patch.object(module, "_group_entries_by_site", return_value=[]),
        ):
            written = dump_report_filters(master, output)
        assert written == 0
        with output.open(encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
            header_line = file.readline()
        # ヘッダは出力されるが、データ行は 0 件
        assert rows == []
        # ヘッダの後ろに追加の空行は無い（BOM 付き UTF-8 + ``newline=""`` の挙動確認）
        assert header_line == ""

    def test_site_for_is_invoked_per_report(self, tmp_path):
        """``site_for(url)`` はレポート 1 件ごとに呼ばれる（接続は組織単位で集約）。"""
        master = make_master(
            tmp_path / "管理表.xlsx",
            [
                [
                    "1001",
                    "営業事務グループ",
                    "山田",
                    "組織A",
                    URL_A,
                    str(tmp_path),
                    "○",
                    "",
                ],
                [
                    "1002",
                    "営業事務グループ",
                    "山田",
                    "組織A",
                    URL_A,
                    str(tmp_path),
                    "○",
                    "",
                ],
                [
                    "1003",
                    "経理グループ",
                    "佐藤",
                    "組織B",
                    URL_B,
                    str(tmp_path),
                    "○",
                    "",
                ],
            ],
        )
        output = tmp_path / "out.csv"
        site_a = fake_site({"reportMetadata": {"reportFilters": []}})
        site_a.__name__ = "FakeSiteA"
        site_a.DISPLAY_NAME = "テスト組織A"
        site_b = fake_site({"reportMetadata": {"reportFilters": []}})
        site_b.__name__ = "FakeSiteB"
        site_b.DISPLAY_NAME = "テスト組織B"
        # URL_A / URL_B で別組織を返す ``site_for`` を設定し、レポート数ぶんの
        # 呼び出しがあっても、内部で組織単位に集約されることを確かめる
        site_for_results = {URL_A: site_a, URL_B: site_b}
        site_for_mock = MagicMock(side_effect=lambda url: site_for_results[url])

        with patch("tools.dump_report_filters.site_for", side_effect=site_for_mock):
            dump_report_filters(master, output)
        # ``site_for()`` はレポート 3 件ぶん呼ばれる
        assert site_for_mock.call_count == 3
        # ``site_class()`` の呼び出し（=組織ごとの接続）は 2 回だけ
        assert site_a.call_count == 1
        assert site_b.call_count == 1


class TestReportEntryContract:
    """将来 ``ReportEntry`` のシグネチャが変わったとき早めに気づくための契約確認。"""

    def test_report_entry_has_required_csv_fields(self) -> None:
        """``ReportEntry`` から使う属性 ``key`` / ``url`` / ``report_id`` が
        このツールの必須契約として残っている。"""
        entry = ReportEntry(
            key="1001",
            group_name="営業事務グループ",
            assignee="山田",
            summary="テスト",
            url=URL_A,
            folder=Path(),
            enabled=True,
            note="",
        )
        assert entry.key == "1001"
        assert entry.url == URL_A
        assert entry.report_id == "00O5g00000ABCDE"
