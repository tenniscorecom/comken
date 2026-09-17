"""``comken.services.salesforce_downloader.sheets.schedule.load_schedule`` を検証する。

`ScheduleRule` の ``raw_*`` パースとプロパティ挙動は ``tests/test_schedule.py``
で担保する（既存テストを壊さない）。ここでは**「Excel から読んで ScheduleRule
のリストにする」**経路と、エラー時の挙動を確かめる。
"""

from pathlib import Path

import pytest

from comken.core.table import Table
from comken.exceptions import (
    ExcelFileNotFoundError,
    MasterDuplicateValueError,
    MasterRowValueError,
)
from comken.services.salesforce_downloader.sheets.schedule import (
    SCHEDULE_SHEET_NAME,
    load_schedule,
)
from comken.toolbox.excel import Excel

# 新スキーマ: 「取得間隔（分）」列は廃止、「日付」列を `曜日` と `祝日対応` の間に
# 追加。順序はこのとおり（Excel の列順は自由だが、テストではこの順で作る）
SCHEDULE_HEADERS = [
    "スケジュールキー",
    "レポートキー",
    "取得頻度",
    "取得時刻",
    "曜日",
    "日付",
    "祝日対応",
    "有効",
]


def make_master_with_schedule(
    path: Path,
    master_rows: list[list],
    schedule_rows: list[list] | None,
) -> Path:
    """レポート管理表と「スケジュール」シートを含むブックを作る。

    ``schedule_rows=None`` のときはスケジュールシート自体を作らない
    （後方互換ケース用）。
    """
    master_headers = [
        "ID",
        "グループ",
        "担当者",
        "概要",
        "Salesforce URL",
        "有効",
        "備考",
    ]
    master_table_rows = [dict(zip(master_headers, row, strict=True)) for row in master_rows]
    with Excel(path) as book:
        book.create_data_sheet("管理表").create_table(
            "管理表", Table(master_headers, master_table_rows)
        )
        if schedule_rows is not None:
            schedule_table_rows = [
                dict(zip(SCHEDULE_HEADERS, row, strict=True)) for row in schedule_rows
            ]
            book.create_data_sheet(SCHEDULE_SHEET_NAME).create_table(
                SCHEDULE_SHEET_NAME, Table(SCHEDULE_HEADERS, schedule_table_rows)
            )
    return path


class TestLoadSchedule:
    """Excel から ScheduleRule へ変換する経路の挙動。"""

    def test_reads_normal_rows_into_schedule_rules(self, tmp_path):
        master = make_master_with_schedule(
            tmp_path / "管理表.xlsx",
            [
                # 管理表本体は load_schedule() の検証対象ではないので空でもよいが、
                # 実際の運用を再現するため1行入れておく
                [
                    "1001",
                    "営業事務グループ",
                    "山田",
                    "顧客一覧",
                    "https://example.com/a/view",
                    "○",
                    "",
                ],
            ],
            schedule_rows=[
                # スケジュールキー / レポートキー / 取得頻度 / 取得時刻 / 曜日 /
                # 日付 / 祝日対応 / 有効 の8列で書く
                ["S001", "1001", "毎週", "09:00", "月", "", "取得しない", "○"],
                ["S002", "1002", "毎日", "10:30", "", "", "取得しない", "○"],
            ],
        )
        rules = load_schedule(master)
        assert [rule.schedule_key for rule in rules] == ["S001", "S002"]
        assert rules[0].weekday == 0  # 月曜
        assert rules[1].run_time is not None
        assert rules[1].run_time.hour == 10

    def test_blank_rows_are_skipped(self, tmp_path):
        master = make_master_with_schedule(
            tmp_path / "管理表.xlsx",
            [
                [
                    "1001",
                    "営業事務グループ",
                    "山田",
                    "顧客一覧",
                    "https://example.com/a/view",
                    "○",
                    "",
                ]
            ],
            schedule_rows=[
                ["S001", "1001", "毎週", "09:00", "月", "", "取得しない", "○"],
                [None] * len(SCHEDULE_HEADERS),  # 空行は読み飛ばす
                ["S002", "1002", "毎日", "10:30", "", "", "取得しない", "○"],
            ],
        )
        rules = load_schedule(master)
        assert [rule.schedule_key for rule in rules] == ["S001", "S002"]

    def test_missing_schedule_sheet_returns_empty_list(self, tmp_path):
        """「スケジュール」シートが無い管理表はエラーにせず空リストを返す（後方互換）。"""
        master = make_master_with_schedule(
            tmp_path / "管理表.xlsx",
            [
                [
                    "1001",
                    "営業事務グループ",
                    "山田",
                    "顧客一覧",
                    "https://example.com/a/view",
                    "○",
                    "",
                ]
            ],
            # スケジュールシート自体を作らない
            schedule_rows=None,
        )
        assert load_schedule(master) == []

    def test_duplicate_schedule_key_raises(self, tmp_path):
        master = make_master_with_schedule(
            tmp_path / "管理表.xlsx",
            [
                [
                    "1001",
                    "営業事務グループ",
                    "山田",
                    "顧客一覧",
                    "https://example.com/a/view",
                    "○",
                    "",
                ]
            ],
            schedule_rows=[
                ["S001", "1001", "毎週", "09:00", "月", "", "取得しない", "○"],
                ["S001", "1002", "毎週", "10:00", "火", "", "取得しない", "○"],  # 重複
            ],
        )
        with pytest.raises(MasterDuplicateValueError) as e:
            load_schedule(master)
        # 業務担当者に「どの値が」「どの見出しで」重複したかが届く
        assert "スケジュールキー" in str(e.value)
        assert "S001" in str(e.value)

    def test_missing_required_value_raises_with_row_number(self, tmp_path):
        """必須列（スケジュールキー）が空のとき、行番号付き ``MasterRowValueError`` で抜ける。"""
        master = make_master_with_schedule(
            tmp_path / "管理表.xlsx",
            [
                [
                    "1001",
                    "営業事務グループ",
                    "山田",
                    "顧客一覧",
                    "https://example.com/a/view",
                    "○",
                    "",
                ]
            ],
            schedule_rows=[
                [
                    "",
                    "1001",
                    "毎週",
                    "09:00",
                    "月",
                    "",
                    "取得しない",
                    "○",
                ],  # スケジュールキー空
            ],
        )
        with pytest.raises(MasterRowValueError) as e:
            load_schedule(master)
        # 見出しの次の行（offset=0, row_number=2）が指摘される
        assert "2 行目" in str(e.value)
        assert "スケジュールキー" in str(e.value)

    def test_invalid_frequency_raises(self, tmp_path):
        """choices に無い取得頻度は ``MasterRowValueError``（=許可された選択肢が並ぶ）。"""
        master = make_master_with_schedule(
            tmp_path / "管理表.xlsx",
            [
                [
                    "1001",
                    "営業事務グループ",
                    "山田",
                    "顧客一覧",
                    "https://example.com/a/view",
                    "○",
                    "",
                ]
            ],
            schedule_rows=[
                ["S001", "1001", "ときどき", "09:00", "", "", "取得しない", "○"],
            ],
        )
        with pytest.raises(MasterRowValueError) as e:
            load_schedule(master)
        assert "取得頻度" in str(e.value)

    def test_blank_enabled_raises(self, tmp_path):
        """「有効」列は既定値なし（書き忘れはエラー）に統一したため、空欄で止まる。"""
        master = make_master_with_schedule(
            tmp_path / "管理表.xlsx",
            [
                [
                    "1001",
                    "営業事務グループ",
                    "山田",
                    "顧客一覧",
                    "https://example.com/a/view",
                    "○",
                    "",
                ]
            ],
            schedule_rows=[
                ["S001", "1001", "毎週", "09:00", "月", "", "取得しない", ""],
            ],
        )
        with pytest.raises(MasterRowValueError) as e:
            load_schedule(master)
        assert "有効" in str(e.value)

    def test_day_of_month_is_parsed(self, tmp_path):
        """「日付」列の数字が ``day_of_month`` プロパティで取り出せる。"""
        master = make_master_with_schedule(
            tmp_path / "管理表.xlsx",
            [
                [
                    "1001",
                    "営業事務グループ",
                    "山田",
                    "顧客一覧",
                    "https://example.com/a/view",
                    "○",
                    "",
                ]
            ],
            schedule_rows=[
                ["S001", "1001", "毎月", "06:00", "", "15", "取得しない", "○"],
            ],
        )
        rules = load_schedule(master)
        assert rules[0].day_of_month == 15
        assert rules[0].month_end is False

    def test_missing_master_file_raises(self, tmp_path):
        """シート無しと「ファイル自体が無い」は別のエラー（後者はそのまま上位へ）。"""
        missing = tmp_path / "無い.xlsx"
        assert not missing.exists()
        with pytest.raises(ExcelFileNotFoundError):
            load_schedule(missing)
