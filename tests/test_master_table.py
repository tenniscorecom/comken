"""Excel の表を設定として読む仕組みを、実際に Excel を作って検証する。

Salesforce に依存しない汎用部分だけを見る（Salesforce 固有の列は
test_salesforce_downloader.py 側）。
"""

from dataclasses import dataclass
from pathlib import Path

import pytest
from openpyxl import load_workbook

from comken.exceptions import (
    MasterColumnNotFoundError,
    MasterDuplicateValueError,
    MasterRowValueError,
    MasterSheetNotDefinedError,
)
from comken.toolbox.excel import ExcelWriter
from comken.toolbox.master_table import MasterRow, column


@dataclass(frozen=True)
class Item(MasterRow):
    """検証用の1行。"""

    SHEET_NAME = "一覧"

    key: int = column("ID", unique=True, help="管理番号")
    name: str = column("名前", help="人が読んで分かる名前")
    source: Path = column("コピー元", help="共有サーバー上のファイル")
    mode: str = column("方式", choices=("毎日", "手動"), help="毎日は自動で取ります")
    enabled: bool = column("有効", default=True, help="使わなくなったら「無効」")


HEADERS = ["ID", "名前", "コピー元", "方式", "有効"]
ROW_A = [1001, "受注一覧", r"\\server\受注\data.csv", "毎日", "有効"]
ROW_B = [1002, "在庫", r"\\server\在庫\data.csv", "手動", "無効"]


def make_sheet(path: Path, rows: list[list], headers: list[str] | None = None) -> Path:
    with ExcelWriter.create(path, "一覧") as book:
        sheet = book.sheet("一覧")
        sheet.write_row(1, headers or HEADERS)
        for offset, row in enumerate(rows):
            sheet.write_row(offset + 2, row)
        book.save()
    return path


class TestLoad:
    """宣言した型のとおりに読める。"""

    def test_reads_rows_with_declared_types(self, tmp_path):
        items = Item.load(make_sheet(tmp_path / "一覧.xlsx", [ROW_A, ROW_B]))
        assert [item.key for item in items] == [1001, 1002]
        assert isinstance(items[0].source, Path)  # 型注釈のとおり Path になる
        assert items[0].enabled is True
        assert items[1].enabled is False  # 「無効」は False

    def test_blank_rows_are_skipped(self, tmp_path):
        """表の下に残った空行は読み飛ばす。"""
        items = Item.load(make_sheet(tmp_path / "一覧.xlsx", [ROW_A, [None] * 5]))
        assert len(items) == 1

    def test_default_is_used_for_blank_cell(self, tmp_path):
        """既定値のある列は空欄でよい。"""
        row = [1001, "受注一覧", r"\\server\a.csv", "毎日", None]
        assert Item.load(make_sheet(tmp_path / "一覧.xlsx", [row]))[0].enabled is True

    def test_blank_without_default_raises(self, tmp_path):
        """既定値の無い列が空なら、その行と列を示して止める。"""
        row = [1001, None, r"\\server\a.csv", "毎日", "有効"]
        with pytest.raises(MasterRowValueError) as e:
            Item.load(make_sheet(tmp_path / "一覧.xlsx", [row]))
        assert "2 行目" in str(e.value)  # 見出しが1行目なので、最初のデータは2行目
        assert "名前" in str(e.value)

    def test_path_without_default_raises(self, tmp_path):
        with pytest.raises(MasterSheetNotDefinedError):
            Item.load()  # PATH も引数も無い


class TestValidation:
    """非エンジニアが編集する表なので、どこが変かを示して止める。"""

    def test_value_outside_choices_raises(self, tmp_path):
        row = [1001, "受注一覧", r"\\server\a.csv", "毎週", "有効"]
        with pytest.raises(MasterRowValueError) as e:
            Item.load(make_sheet(tmp_path / "一覧.xlsx", [row]))
        assert "「毎日」か「手動」" in str(e.value)  # 書ける値を示す

    def test_non_numeric_key_raises(self, tmp_path):
        row = ["A001", "受注一覧", r"\\server\a.csv", "毎日", "有効"]
        with pytest.raises(MasterRowValueError) as e:
            Item.load(make_sheet(tmp_path / "一覧.xlsx", [row]))
        assert "数字" in str(e.value)

    def test_duplicate_unique_value_raises(self, tmp_path):
        rows = [ROW_A, [1001, "別の名前", r"\\server\b.csv", "手動", "有効"]]
        with pytest.raises(MasterDuplicateValueError) as e:
            Item.load(make_sheet(tmp_path / "一覧.xlsx", rows))
        assert "ID" in str(e.value)

    def test_missing_header_raises_with_existing_headers(self, tmp_path):
        """見出しを変えられたら、今ある見出しを示して止める。"""
        headers = ["ID", "名称", "コピー元", "方式", "有効"]  # 「名前」を「名称」に変えた
        with pytest.raises(MasterColumnNotFoundError) as e:
            Item.load(make_sheet(tmp_path / "一覧.xlsx", [ROW_A], headers))
        assert "名前" in str(e.value)
        assert "名称" in str(e.value)  # 今ある見出しも出す


class TestTemplate:
    """雛形は、そのまま読み込める状態で作られる。"""

    def test_generated_template_can_be_loaded(self, tmp_path):
        """**雛形と読み込みで列がズレない**（同じ宣言から作るため）。"""
        example = {
            "key": 1001,
            "name": "受注一覧",
            "source": Path(r"\\server\受注\data.csv"),
            "mode": "毎日",
            "enabled": True,
        }
        path = Item.create_template(tmp_path / "一覧.xlsx", [example])
        items = Item.load(path)
        assert len(items) == 1
        assert items[0].key == 1001
        assert items[0].enabled is True  # True は「有効」として書かれ、読み戻せる

    def test_headers_are_written_in_declaration_order(self, tmp_path):
        path = Item.create_template(tmp_path / "一覧.xlsx")
        sheet = load_workbook(path)["一覧"]
        assert [cell.value for cell in sheet[1]] == HEADERS

    def test_guide_sheet_lists_every_column(self, tmp_path):
        """非エンジニアが1枚で分かるよう、列ごとの説明を書く。"""
        path = Item.create_template(tmp_path / "一覧.xlsx")
        guide = load_workbook(path)["記入方法"]
        text = "\n".join(str(cell.value) for row in guide.iter_rows() for cell in row)
        for header in HEADERS:
            assert header in text
        assert "管理番号" in text  # help がそのまま出る
        assert "「毎日」か「手動」" in text  # 選択肢は書き方として出す

    def test_table_is_created(self, tmp_path):
        """Excel のテーブルにしておくと、行を足すのが楽になる。"""
        path = Item.create_template(tmp_path / "一覧.xlsx", [{"key": 1, "name": "a"}])
        assert load_workbook(path)["一覧"].tables
