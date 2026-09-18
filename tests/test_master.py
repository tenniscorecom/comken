"""comken.services.salesforce_downloader.sheets.master の ReportEntry 固有の列を検証する。

汎用の MasterRow / column() 機構は tests/test_master_table.py 側でカバーする。
ここでは ReportEntry に追加した列（`exceeds_row_limit` / `use_soql` と 9291 向け
`report_name` / `save_mode`）の読み取りと、列が無い既存管理表でも既定値で読める
こと（後方互換）だけを見る。
"""

from pathlib import Path

import pytest

from comken.core.table import Table
from comken.exceptions import MasterRowValueError
from comken.services.salesforce_downloader.sheets.master import ReportEntry, load_master
from comken.toolbox.excel import Excel

URL = "https://example--sandbox.sandbox.my.salesforce.com/lightning/r/Report/00O5g00000ABCDE/view"

HEADERS = [
    "ID",
    "グループ",
    "担当者",
    "概要",
    "Salesforce URL",
    "有効",
    "0件あり",
    "2000件超",
    "SOQL",
    "出力ファイル名",
    "保存方式",
    "備考",
]

# 「2000件超」「SOQL」列を追加する前の古い管理表（後方互換の確認用）。
# 9291 向けの「出力ファイル名」「保存方式」列は、新しい仕様で必須列として
# 足したため、ここにも含めて ``test_missing_columns_default_to_false`` が
# 「2000件超」「SOQL」列の後方互換に集中できるようにしている
LEGACY_HEADERS = [
    "ID",
    "グループ",
    "担当者",
    "概要",
    "Salesforce URL",
    "有効",
    "0件あり",
    "出力ファイル名",
    "保存方式",
    "備考",
]


def make_master(path: Path, headers: list[str], rows: list[list]) -> Path:
    """管理表（Excel）を作る。"""
    table_rows = [dict(zip(headers, row, strict=True)) for row in rows]
    with Excel(path) as book:
        book.create_data_sheet("管理表").create_table("管理表", Table(headers, table_rows))
    return path


def _row(
    *,
    exceeds: str,
    soql: str,
    report_name: str = "顧客一覧.csv",
    save_mode: str = "上書き",
) -> list:
    return [
        "1001",
        "営業本部",
        "山田太郎",
        "顧客一覧",
        URL,
        "○",
        "×",
        exceeds,
        soql,
        report_name,
        save_mode,
        "",
    ]


class TestExceedsRowLimitAndUseSoql:
    """「2000件超」「SOQL」列の読み取り。"""

    def test_reads_maru_as_true(self, tmp_path):
        master = make_master(tmp_path / "管理表.xlsx", HEADERS, [_row(exceeds="○", soql="○")])
        entry = load_master(master)["1001"]
        assert entry.exceeds_row_limit is True
        assert entry.use_soql is True

    def test_reads_batsu_as_false(self, tmp_path):
        master = make_master(tmp_path / "管理表.xlsx", HEADERS, [_row(exceeds="×", soql="×")])
        entry = load_master(master)["1001"]
        assert entry.exceeds_row_limit is False
        assert entry.use_soql is False

    def test_missing_columns_default_to_false(self, tmp_path):
        """列が無い既存の管理表でも読める（後方互換）。既定は両方「×」相当。"""
        rows = [
            [
                "1001",
                "営業本部",
                "山田太郎",
                "顧客一覧",
                URL,
                "○",
                "×",
                "顧客一覧.csv",
                "上書き",
                "",
            ]
        ]
        master = make_master(tmp_path / "管理表.xlsx", LEGACY_HEADERS, rows)
        entry = load_master(master)["1001"]
        assert entry.exceeds_row_limit is False
        assert entry.use_soql is False


class TestDirectConstruction:
    """ReportEntry を直接組み立てるとき（テストの他の場所で使う形）も既定値が効く。"""

    def test_defaults_when_omitted(self):
        entry = ReportEntry(
            key="1001",
            summary="顧客一覧",
            url=URL,
            group="営業本部",
            assignee="山田太郎",
            enabled=True,
            allow_empty=False,
            report_name="顧客一覧.csv",
            save_mode="上書き",
        )
        assert entry.exceeds_row_limit is False
        assert entry.use_soql is False


class TestReportNameAndSaveMode:
    """9291 向け出力に使う「出力ファイル名」「保存方式」列の読み取り。"""

    def test_reads_overwrite_and_new_modes(self, tmp_path):
        master = make_master(
            tmp_path / "管理表.xlsx",
            HEADERS,
            [_row(exceeds="×", soql="×", report_name="月次受注.csv", save_mode="上書き")],
        )
        entry = load_master(master)["1001"]
        assert entry.report_name == "月次受注.csv"
        assert entry.save_mode == "上書き"

    def test_save_mode_new_is_read(self, tmp_path):
        master = make_master(
            tmp_path / "管理表.xlsx",
            HEADERS,
            [_row(exceeds="×", soql="×", report_name="月次受注.csv", save_mode="新規")],
        )
        entry = load_master(master)["1001"]
        assert entry.save_mode == "新規"

    def test_invalid_save_mode_raises(self, tmp_path):
        """`choices` で `上書き`/`新規` 以外を弾く（タイポの設定ミスを即座に知らせる）。"""
        master = make_master(
            tmp_path / "管理表.xlsx",
            HEADERS,
            [_row(exceeds="×", soql="×", report_name="月次受注.csv", save_mode="追記")],
        )
        with pytest.raises(MasterRowValueError) as caught:
            load_master(master)
        assert "保存方式" in str(caught.value)

    def test_blank_report_name_raises(self, tmp_path):
        """空欄はエラー（必須列として書く必要を明示するため、`enabled` と同じ運用）。"""
        master = make_master(
            tmp_path / "管理表.xlsx",
            HEADERS,
            [_row(exceeds="×", soql="×", report_name="", save_mode="上書き")],
        )
        with pytest.raises(MasterRowValueError) as caught:
            load_master(master)
        assert "出力ファイル名" in str(caught.value)


class TestDirectConstructionRpaColumns:
    """ReportEntry を直接組み立てるとき、`report_name` / `save_mode` も必須。"""

    def test_direct_construction_requires_both_columns(self):
        with pytest.raises(TypeError):
            ReportEntry(  # type: ignore[call-arg]
                key="1001",
                summary="顧客一覧",
                url=URL,
                group="営業本部",
                assignee="山田太郎",
                enabled=True,
                allow_empty=False,
                exceeds_row_limit=False,
                use_soql=False,
                report_name="顧客一覧.csv",
                # save_mode を渡さない → 必須列の欠け
            )
