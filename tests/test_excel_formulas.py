"""Excel の数式セル読み書きまわりの契約テスト。"""

import re
import tempfile
import zipfile
from pathlib import Path

import pytest
from openpyxl import Workbook

from comken.core.table import Table
from comken.exceptions import TableFormulaOverwriteError
from comken.toolbox.excel import Excel


def _book_with_cached_formulas(
    path: Path,
    *,
    sheet_name: str,
    formulas_with_values: dict[str, tuple[str, str]],
) -> None:
    """数式セルにキャッシュ値（計算結果）を埋めた xlsx を作る。

    openpyxl は保存時に再計算しないので、保存後の zip 内
    ``xl/worksheets/sheet1.xml`` を直接編集して ``<c><f>...</f><v>...</v></c>``
    の ``<v>`` に計算結果を入れる。Excel が開いたときは「キャッシュ済み」と
    みなされ、``Excel._cached_range`` は再計算しないで値を返す。
    """
    workbook = Workbook()
    sheet = workbook.active
    if sheet is None:
        raise AssertionError("Workbook に active sheet がない")
    sheet.title = sheet_name
    for coord, formula_value in formulas_with_values.items():
        sheet[coord] = formula_value[0]
    workbook.save(path)
    # zip 内のシート XML に <v> を埋め込んでから再圧縮する。
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_path = Path(tmp_str)
        with zipfile.ZipFile(path) as archive:
            archive.extractall(tmp_path)
        sheet_xml_path = tmp_path / "xl" / "worksheets" / "sheet1.xml"
        text = sheet_xml_path.read_text(encoding="utf-8")
        for coord, formula_value in formulas_with_values.items():
            cached = formula_value[1]
            pattern = re.compile(
                r'(<c r="' + re.escape(coord) + r'"[^/>]*>)'
                r"(<f[^<]*</f>)"
                r"(<v[^<]*</v>)"
                r"(</c>)"
            )
            replacement = r"\1\2<v>" + cached + r"</v>\4"
            text, count = pattern.subn(replacement, text)
            if count == 0:
                raise AssertionError(f"数式セルが見つかりません: {coord}")
        sheet_xml_path.write_text(text, encoding="utf-8")
        path.unlink()
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(tmp_path.rglob("*")):
                if file.is_file():
                    archive.write(file, file.relative_to(tmp_path).as_posix())


def test_read_value_returns_cached_formula_result(tmp_path: Path) -> None:
    """read_value() は数式セルのとき ``=...`` ではなく計算結果を返す。"""
    path = tmp_path / "cached.xlsx"
    _book_with_cached_formulas(
        path,
        sheet_name="集計",
        formulas_with_values={"A2": ("=A1*2", "4")},
    )
    with Excel(path) as excel:
        sheet = excel.sheet("集計")
        assert sheet.read_value("A2") == 4


def test_read_formula_returns_formula_string(tmp_path: Path) -> None:
    """read_formula() はセルの数式本体をそのまま返す。"""
    path = tmp_path / "formula.xlsx"
    _book_with_cached_formulas(
        path,
        sheet_name="集計",
        formulas_with_values={"A2": ("=A1*2", "4")},
    )
    with Excel(path) as excel:
        sheet = excel.sheet("集計")
        assert sheet.read_formula("A2") == "=A1*2"


def test_read_value_returns_raw_value_when_no_formula(tmp_path: Path) -> None:
    """数式が無いセルの read_value() は従来どおりの値を返す。"""
    path = tmp_path / "plain.xlsx"
    with Excel(path) as excel:
        sheet = excel.create_sheet("集計")
        sheet.write_value("A1", "hello")
        sheet.write_value("B1", 42)
        assert sheet.read_value("A1") == "hello"
        assert sheet.read_value("B1") == 42


def test_read_formula_returns_empty_when_not_a_formula(tmp_path: Path) -> None:
    """数式でないセルの read_formula() は空文字を返す。"""
    path = tmp_path / "plain.xlsx"
    with Excel(path) as excel:
        sheet = excel.create_sheet("集計")
        sheet.write_value("A1", "hello")
        assert sheet.read_formula("A1") == ""


def test_replace_with_formula_raises_default(tmp_path: Path) -> None:
    """人が入れた数式を含むテーブルへの replace() は既定で例外を出す。"""
    path = tmp_path / "formula-table.xlsx"
    with Excel(path) as excel:
        table = excel.create_data_sheet("顧客").create_table(
            "顧客", Table(["ID", "合計"], [{"ID": "001", "合計": 100}])
        )
        # 人が「合計」列へ入れた数式
        table._worksheet["B2"] = "=SUM(B2:B3)"

        with pytest.raises(TableFormulaOverwriteError) as exc_info:
            table.replace([{"ID": "002", "合計": 200}])

        assert "B2" in str(exc_info.value)
        # 数式セルはそのまま残っている
        assert table._worksheet["B2"].value == "=SUM(B2:B3)"


def test_replace_with_formula_overwrites_when_allowed(tmp_path: Path) -> None:
    """allow_formula_overwrite=True のときは従来どおり値で上書きする。"""
    path = tmp_path / "formula-overwrite.xlsx"
    with Excel(path) as excel:
        table = excel.create_data_sheet("顧客").create_table(
            "顧客", Table(["ID", "合計"], [{"ID": "001", "合計": 100}])
        )
        table._worksheet["B2"] = "=SUM(B2:B3)"
        table.replace(
            [{"ID": "002", "合計": 200}],
            allow_formula_overwrite=True,
        )
        assert table._worksheet["B2"].value == 200


def test_replace_without_formula_succeeds(tmp_path: Path) -> None:
    """数式が無いテーブルへの replace() は従来どおり通る。"""
    path = tmp_path / "no-formula.xlsx"
    with Excel(path) as excel:
        table = excel.create_data_sheet("顧客").create_table("顧客", Table(["ID"], [{"ID": "001"}]))
        table.replace([{"ID": "002"}])
        assert table.read().read() == [{"ID": "002"}]


def test_replace_only_checks_data_rows_not_header(tmp_path: Path) -> None:
    """見出し行の先頭が ``=`` でも例外は出さない（データ部のみ検査）。"""
    path = tmp_path / "header-formula.xlsx"
    with Excel(path) as excel:
        # 見出し行に ``=`` 始まりの文字列を入れる異常系。通常起こらないが、
        # replace() の検査範囲がデータ部に限定されていることを確認する。
        excel.create_data_sheet("顧客").create_table("顧客", Table(["ID"], [{"ID": "001"}]))
        excel._workbook["PY_顧客"]["A1"] = "=壊れ見出し"
        # データ部に数式が無ければ通る（検査は min_row+1 から max_row のみ）。
        excel.data_sheet("顧客").table().replace([{"ID": "002"}])
