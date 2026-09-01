"""``comken.services.salesforce_downloader.schedule.load_schedule`` を検証する。

`ScheduleRule.from_row()` のパース挙動は ``tests/test_schedule.py`` で担保する
（既存テストを壊さない）。ここでは**「Excel から読んで ScheduleRule のリストにする」**
経路と、エラー時の挙動を確かめる。
"""

from pathlib import Path

import pytest

from comken.core.table import Table
from comken.exceptions import (
    ExcelFileNotFoundError,
    ScheduleDuplicateKeyError,
    ScheduleRequiredValueMissingError,
    ScheduleRowValueError,
    ScheduleWeekdayInvalidError,
)
from comken.services.salesforce_downloader.schedule import (
    SCHEDULE_SHEET_NAME,
    ScheduleRule,
    load_schedule,
)
from comken.toolbox.excel import Excel

SCHEDULE_HEADERS = [
    "スケジュールキー",
    "レポートキー",
    "取得頻度",
    "取得時刻",
    "曜日",
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
        "概要",
        "Salesforce URL",
        "出力形式",
        "保存先",
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
                ["1001", "顧客一覧", "https://example.com/a/view", "定期", str(tmp_path), "○", ""],
            ],
            schedule_rows=[
                ["S001", "1001", "毎週", "09:00", "月", "取得しない", "○"],
                ["S002", "1002", "毎日", "10:30", "", "取得しない", "○"],
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
            [["1001", "顧客一覧", "https://example.com/a/view", "定期", str(tmp_path), "○", ""]],
            schedule_rows=[
                ["S001", "1001", "毎週", "09:00", "月", "取得しない", "○"],
                [None] * len(SCHEDULE_HEADERS),  # 空行は読み飛ばす
                ["S002", "1002", "毎日", "10:30", "", "取得しない", "○"],
            ],
        )
        rules = load_schedule(master)
        assert [rule.schedule_key for rule in rules] == ["S001", "S002"]

    def test_missing_schedule_sheet_returns_empty_list(self, tmp_path):
        """「スケジュール」シートが無い管理表はエラーにせず空リストを返す（後方互換）。"""
        master = make_master_with_schedule(
            tmp_path / "管理表.xlsx",
            [["1001", "顧客一覧", "https://example.com/a/view", "定期", str(tmp_path), "○", ""]],
            # スケジュールシート自体を作らない
            schedule_rows=None,
        )
        assert load_schedule(master) == []

    def test_duplicate_schedule_key_raises(self, tmp_path):
        master = make_master_with_schedule(
            tmp_path / "管理表.xlsx",
            [["1001", "顧客一覧", "https://example.com/a/view", "定期", str(tmp_path), "○", ""]],
            schedule_rows=[
                ["S001", "1001", "毎週", "09:00", "月", "取得しない", "○"],
                ["S001", "1002", "毎週", "10:00", "火", "取得しない", "○"],  # 重複
            ],
        )
        with pytest.raises(ScheduleDuplicateKeyError) as e:
            load_schedule(master)
        # 業務担当者に「どちらの値か」「何行目か」が届く
        assert "S001" in str(e.value)
        assert "3 行目" in str(e.value)  # 重複の2行目は offset=1 で row_number=3

    def test_invalid_weekday_raises_with_row_number(self, tmp_path):
        """曜日が壊れていると、メッセージに行番号が入る（業務担当者が直せるように）。"""
        master = make_master_with_schedule(
            tmp_path / "管理表.xlsx",
            [["1001", "顧客一覧", "https://example.com/a/view", "定期", str(tmp_path), "○", ""]],
            schedule_rows=[
                ["S001", "1001", "毎週", "09:00", "不明", "取得しない", "○"],
            ],
        )
        with pytest.raises(ScheduleRowValueError) as e:
            load_schedule(master)
        # 見出しの次の行（offset=0, row_number=2）が指摘される
        assert "2 行目" in str(e.value)
        # 元の例外（曜日エラー）が連鎖している
        assert isinstance(e.value.__cause__, ScheduleWeekdayInvalidError)

    def test_missing_required_value_raises_with_row_number(self, tmp_path):
        master = make_master_with_schedule(
            tmp_path / "管理表.xlsx",
            [["1001", "顧客一覧", "https://example.com/a/view", "定期", str(tmp_path), "○", ""]],
            schedule_rows=[
                ["", "1001", "毎週", "09:00", "月", "取得しない", "○"],  # スケジュールキー空
            ],
        )
        with pytest.raises(ScheduleRowValueError) as e:
            load_schedule(master)
        assert "2 行目" in str(e.value)
        assert isinstance(e.value.__cause__, ScheduleRequiredValueMissingError)

    def test_missing_master_file_raises(self, tmp_path):
        """シート無しと「ファイル自体が無い」は別のエラー（後者はそのまま上位へ）。"""
        missing = tmp_path / "無い.xlsx"
        assert not missing.exists()
        with pytest.raises(ExcelFileNotFoundError):
            load_schedule(missing)


# 後方互換のサニティチェック: 既存 `ScheduleRule.from_row()` の呼び出し形式が
# 今まで通り動くことを確認する（タスク #2 の「``tests/test_schedule.py`` の
# 既存呼び出し ``ScheduleRule.from_row(row)`` が今まで通り動くこと」を保証）。
def test_existing_from_row_signature_still_works():
    rule = ScheduleRule.from_row(
        {
            "スケジュールキー": "S1",
            "レポートキー": "1001",
            "取得頻度": "毎日",
            "取得時刻": "09:00",
            "有効": "○",
        }
    )
    assert rule.schedule_key == "S1"
