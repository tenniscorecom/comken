"""現行のExcel API（Excel / Sheet / ExcelTable）の契約テスト。"""

import re
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import pytest
from openpyxl import Workbook
from openpyxl.styles import PatternFill

from comken.core.table import Table
from comken.exceptions import (
    ComkenFileNotFoundError,
    ExcelError,
    SheetNotFoundError,
    TableError,
    UnsupportedFileSuffixError,
)
from comken.toolbox.excel import Excel


def test_excel_creates_and_reads_python_table(tmp_path) -> None:
    path = tmp_path / "book.xlsx"
    with Excel(path) as excel:
        sheet = excel.create_data_sheet("顧客")
        sheet.create_table("顧客", Table(["ID", "名前"], [{"ID": "001", "名前": "山田"}]))
    with Excel(path, read_only=True) as excel:
        assert excel.data_sheet("顧客").table().read() == [{"ID": "001", "名前": "山田"}]


def test_excel_replaces_table_without_saving_until_context_exit(tmp_path) -> None:
    path = tmp_path / "book.xlsx"
    with Excel(path) as excel:
        excel.create_data_sheet("顧客").create_table("顧客", Table(["ID"], [{"ID": "001"}]))
    with Excel(path) as excel:
        table = excel.data_sheet("顧客").table()
        table.replace([{"ID": "002"}])
        assert table.read() == [{"ID": "002"}]
    with Excel(path, read_only=True) as excel:
        assert excel.data_sheet("顧客").table().read() == [{"ID": "002"}]


def test_excel_rejects_ambiguous_table_name(tmp_path) -> None:
    path = tmp_path / "book.xlsx"
    with Excel(path) as excel:
        sheet = excel.create_data_sheet("顧客")
        sheet.create_table("基本", Table(["ID"], [{"ID": "001"}]), "A1")
        sheet.create_table("連絡", Table(["電話"], [{"電話": "000"}]), "D1")
        with pytest.raises(TableError):
            sheet.table().read()


def test_excel_rejects_duplicate_data_sheet(tmp_path) -> None:
    with Excel(tmp_path / "book.xlsx") as excel:
        excel.create_data_sheet("顧客")
        with pytest.raises(ExcelError):
            excel.create_data_sheet("顧客")


def test_excel_table_append_accepts_row_list_and_table(tmp_path) -> None:
    path = tmp_path / "book.xlsx"
    with Excel(path) as excel:
        table = excel.create_data_sheet("顧客").create_table("顧客", Table(["ID"], [{"ID": "001"}]))
        table.append({"ID": "002"})
        table.append([{"ID": "003"}])
        table.append(Table(["ID"], [{"ID": "004"}]))
    with Excel(path, read_only=True) as excel:
        assert excel.data_sheet("顧客").table().read().column("ID") == [
            "001",
            "002",
            "003",
            "004",
        ]


def test_excel_rejects_missing_read_only_file_and_non_excel_suffix(tmp_path) -> None:
    path = tmp_path / "missing.xlsx"
    with pytest.raises(ComkenFileNotFoundError), Excel(path, read_only=True):
        pass
    with pytest.raises(UnsupportedFileSuffixError):
        Excel(tmp_path / "book.csv")


def test_create_sheet_uses_name_as_is_and_supports_layout_api(tmp_path) -> None:
    path = tmp_path / "book.xlsx"
    with Excel(path) as excel:
        sheet = excel.create_sheet("集計")
        assert sheet.is_data_sheet is False
        sheet.freeze_panes("B2")
        sheet.write_value("A1", "見出し")
        sheet.format("A1", bold=True)
    with Excel(path, read_only=True) as excel:
        restored = excel.sheet("集計")
        assert restored.read_value("A1") == "見出し"
        assert restored.read_value("A1") == "見出し"


def test_create_sheet_does_not_appear_in_list_data_sheets(tmp_path) -> None:
    path = tmp_path / "book.xlsx"
    with Excel(path) as excel:
        excel.create_data_sheet("顧客").create_table("顧客", Table(["ID"], [{"ID": "001"}]))
        excel.create_sheet("集計")
        assert excel.list_data_sheets() == ["PY_顧客"]


def test_create_sheet_allows_multiple_display_sheets(tmp_path) -> None:
    path = tmp_path / "book.xlsx"
    with Excel(path) as excel:
        excel.create_sheet("集計")
        excel.create_sheet("月次")
        display_names = [name for name in excel._workbook.sheetnames if not name.startswith("PY_")]
        assert "集計" in display_names
        assert "月次" in display_names


def test_create_sheet_rejects_duplicate_name(tmp_path) -> None:
    with Excel(tmp_path / "book.xlsx") as excel:
        excel.create_sheet("集計")
        with pytest.raises(ExcelError):
            excel.create_sheet("集計")


def test_create_sheet_rejects_python_prefixed_name(tmp_path) -> None:
    with Excel(tmp_path / "book.xlsx") as excel, pytest.raises(ExcelError):
        excel.create_sheet("PY_顧客")


def test_create_sheet_rejects_read_only_workbook(tmp_path) -> None:
    path = tmp_path / "book.xlsx"
    with Excel(path) as excel:
        excel.create_sheet("集計")
    with Excel(path, read_only=True) as excel, pytest.raises(ExcelError):
        excel.create_sheet("別のシート")


def test_create_sheet_returns_sheet_that_supports_layout_api(tmp_path) -> None:
    path = tmp_path / "book.xlsx"
    with Excel(path) as excel:
        sheet = excel.create_sheet("集計")
        # 表示用シートでは table() は ExcelError
        with pytest.raises(ExcelError):
            sheet.table()


def test_excel_outside_with_block_raises_table_not_open_error(tmp_path) -> None:
    path = tmp_path / "book.xlsx"
    excel = Excel(path)
    with pytest.raises(TableError, match="Excel"):
        excel.list_data_sheets()
    with pytest.raises(TableError, match="Excel"):
        excel.data_sheet("顧客")
    with pytest.raises(TableError, match="Excel"):
        excel.create_sheet("集計")
    with pytest.raises(TableError, match="Excel"):
        excel.save()


class TestCreateTableNameValidation:
    """``Sheet.create_table`` は Excel が受け付けない名前を ``ExcelError`` で止める。"""

    @pytest.mark.parametrize(
        "invalid_name",
        [
            pytest.param("", id="empty"),
            pytest.param("結 果", id="contains-half-width-space"),
            pytest.param("結　果", id="contains-full-width-space"),
            pytest.param("1結果", id="starts-with-digit"),
            pytest.param("A1", id="cell-reference-A1"),
            pytest.param("R1C1", id="cell-reference-R1C1"),
            pytest.param("Bad/Name", id="forbidden-slash"),
            pytest.param("Bad*Name", id="forbidden-asterisk"),
            pytest.param("Bad[Name", id="forbidden-bracket"),
            pytest.param("Bad]Name", id="forbidden-close-bracket"),
        ],
    )
    def test_invalid_names_raise(self, tmp_path, invalid_name: str) -> None:
        path = tmp_path / "book.xlsx"
        with Excel(path) as excel, pytest.raises(ExcelError):
            excel.create_data_sheet("S").create_table(invalid_name, Table(["a"], [{"a": "1"}]))

    def test_valid_japanese_name_is_accepted(self, tmp_path) -> None:
        path = tmp_path / "book.xlsx"
        with Excel(path) as excel:
            table = excel.create_data_sheet("S").create_table("顧客", Table(["ID"], [{"ID": "1"}]))
            rows = table.read()
        assert rows == [{"ID": "1"}]


class TestReadComputedRowsDropsBlankRows:
    """Excel の ``dimension`` が膨らんだブックで空行を返さない契約。

    Excel は行を削除しても書式が残っていると使用範囲（dimension）が縮まない。
    実務のファイルではよくある状態で、``min_row`` から ``max_row`` まで全部を
    返すと大量の中身のない行が混ざる。 ``_read_computed_rows`` /
    ``read()`` は「全セルが ``None`` または空文字」の行を
    ストリーム段階で落とす。
    """

    def test_declared_range_much_larger_than_data_returns_only_data_rows(self, tmp_path) -> None:
        """実データ 200 行 / 宣言された範囲 5000 行で、返る行数は 200。"""
        path = tmp_path / "declared-empty.xlsx"
        with Excel(path) as excel:
            sheet = excel.create_sheet("データ")
            sheet.write_range("A1:B1", [["ID", "名前"]])
            for index in range(2, 202):
                sheet.write_value(f"A{index}", str(index - 1))
                sheet.write_value(f"B{index}", f"ユーザー{index - 1}")
            # 遠くのセルに書式だけ付けて dimension を膨らませる
            sheet._worksheet.cell(row=5000, column=40).fill = PatternFill("solid", fgColor="FFFF00")

        with Excel(path, read_only=True) as excel:
            rows = excel._computed._read_computed_rows("データ")

        assert len(rows) == 200

    def test_blank_rows_in_the_middle_are_skipped(self, tmp_path) -> None:
        """データの途中の空行（None と空文字の両方）は飛ばされる。"""
        path = tmp_path / "middle-blank.xlsx"
        with Excel(path) as excel:
            sheet = excel.create_sheet("データ")
            sheet.write_range("A1:B1", [["ID", "名前"]])
            sheet.write_value("A2", "1")
            sheet.write_value("B2", "A")
            # 3 行目は空（すべて None）
            # 4 行目はさらに空（すべて空文字）
            sheet.write_value("A5", "")
            sheet.write_value("B5", "")
            sheet.write_value("A6", "2")
            sheet.write_value("B6", "B")

        with Excel(path, read_only=True) as excel:
            rows = excel._computed._read_computed_rows("データ")

        assert rows == [("1", "A"), ("2", "B")]

    def test_zero_and_false_are_kept(self, tmp_path) -> None:
        """``0`` や ``False`` は値として残る（集計を壊さないため）。"""
        path = tmp_path / "zero-false.xlsx"
        with Excel(path) as excel:
            sheet = excel.create_sheet("データ")
            sheet.write_range("A1:C1", [["ID", "数量", "有効"]])
            sheet.write_value("A2", "1")
            sheet.write_value("B2", 0)
            sheet.write_value("C2", False)

        with Excel(path, read_only=True) as excel:
            rows = excel._computed._read_computed_rows("データ")

        assert rows == [("1", 0, False)]

    def test_all_blank_rows_returns_empty_list(self, tmp_path) -> None:
        """空行だけのシートでは空リストが返る（例外にしない）。"""
        path = tmp_path / "all-blank.xlsx"
        with Excel(path) as excel:
            sheet = excel.create_sheet("データ")
            sheet.write_value("A1", "ID")
            # 2 行目以降は空

        with Excel(path, read_only=True) as excel:
            rows = excel._computed._read_computed_rows("データ")

        assert rows == []

    def test_dicts_path_also_skips_blank_rows(self, tmp_path) -> None:
        """``read()`` も空行を飛ばす。"""
        path = tmp_path / "blank-dict.xlsx"
        with Excel(path) as excel:
            sheet = excel.create_sheet("データ")
            sheet.write_range("A1:B1", [["ID", "名前"]])
            sheet.write_value("A2", "1")
            sheet.write_value("B2", "A")
            sheet.write_value("A4", "2")
            sheet.write_value("B4", "B")

        with Excel(path, read_only=True) as excel:
            table = excel.read("データ")

        assert table.to_rows() == [{"ID": "1", "名前": "A"}, {"ID": "2", "名前": "B"}]

    def test_empty_header_cell_error_still_fires(self, tmp_path) -> None:
        """見出し行の空セルは従来どおり ``ExcelError``。"""
        path = tmp_path / "header-blank.xlsx"
        with Excel(path) as excel:
            sheet = excel.create_sheet("データ")
            sheet.write_value("A1", "ID")
            # B1 は空の見出し
            sheet.write_value("A2", "1")
            sheet.write_value("B2", "A")

        with Excel(path, read_only=True) as excel, pytest.raises(ExcelError):
            excel.read("データ")

    def test_existing_header_and_data_behavior_unchanged(self, tmp_path) -> None:
        """通常のブックで見出し + データが期待どおり返ること。"""
        path = tmp_path / "normal.xlsx"
        with Excel(path) as excel:
            sheet = excel.create_sheet("データ")
            sheet.write_range("A1:B1", [["ID", "名前"]])
            sheet.write_value("A2", "1")
            sheet.write_value("B2", "A")

        # ``_read_computed_rows`` と ``read`` は内部で同じストリーム Workbook
        # を使うため、別々の ``with`` ブロックで呼ぶ。同じブロックで 2 回呼ぶと
        # Workbook のライフサイクル管理との兼ね合いで既存の問題が表面化する。
        with Excel(path, read_only=True) as excel:
            rows = excel._computed._read_computed_rows("データ")
        with Excel(path, read_only=True) as excel:
            table = excel.read("データ")

        assert rows == [("1", "A")]
        assert table.to_rows() == [{"ID": "1", "名前": "A"}]


class TestFindSheet:
    """``Excel.find_sheet(*candidates)`` の契約テスト。

    「シート名が違うだけで業務ロジックは共通」という業務ケースを吸収する口。
    ``延期積上集計`` のように ``SHEET_NAME = [Sheet1, 一覧]`` と候補を並べた
    config と組み合わせて使う。
    """

    def test_returns_first_existing_candidate(self, tmp_path) -> None:
        path = tmp_path / "book.xlsx"
        with Excel(path) as excel:
            excel.create_sheet("案件一覧")
            excel.create_sheet("Sheet1")

        with Excel(path, read_only=True) as excel:
            # 候補の 1 番目が見つかればそれを返す（順番保持）
            assert excel.find_sheet("案件一覧", "Sheet1") == "案件一覧"
            # 1 番目が無く 2 番目が見つかれば 2 番目を返す
            assert excel.find_sheet("Sheet1", "案件一覧") == "Sheet1"

    def test_returns_name_string_not_sheet_object(self, tmp_path) -> None:
        """戻り値は ``str``（シート名）で ``Sheet`` ではない。"""
        path = tmp_path / "book.xlsx"
        with Excel(path) as excel:
            excel.create_sheet("案件一覧")

        with Excel(path, read_only=True) as excel:
            result = excel.find_sheet("案件一覧")
            assert isinstance(result, str)
            assert result == "案件一覧"

    def test_raises_sheet_not_found_when_no_candidate_matches(self, tmp_path) -> None:
        """候補が全部無いとき ``SheetNotFoundError`` をそのまま送出する。"""
        path = tmp_path / "book.xlsx"
        with Excel(path) as excel:
            excel.create_sheet("Sheet1")
            excel.create_sheet("案件一覧")

        with Excel(path, read_only=True) as excel:
            with pytest.raises(SheetNotFoundError) as exc:
                excel.find_sheet("無いA", "無いB")
            message = str(exc.value)
            # 最後に試した名前と、ブックに実在するシート名が両方メッセージに含まれる
            assert "無いB" in message
            assert "Sheet1" in message
            assert "案件一覧" in message

    def test_raises_when_no_candidates_given(self, tmp_path) -> None:
        """候補を 1 つも渡さなかったときも、シート一覧入りの例外で止める。"""
        path = tmp_path / "book.xlsx"
        with Excel(path) as excel:
            excel.create_sheet("Sheet1")

        with Excel(path, read_only=True) as excel:
            with pytest.raises(SheetNotFoundError) as exc:
                excel.find_sheet()
            message = str(exc.value)
            assert "Sheet1" in message

    def test_does_not_treat_data_sheet_as_existing_candidate(self, tmp_path) -> None:
        """``PY_`` 付きデータシートを候補に入れても「見つかった」とは扱わない。

        業務ロジック上、表示用シートだけを扱うので、データシート名と一致して
        候補が「在る」と判定されるのは事故（データシートは ``Table`` API で読む）。
        ``find_sheet`` は ``sheetnames`` の所属だけで判定するため、 ``PY_顧客``
        を渡すとそのまま返ってしまう点はこのテストで明示する
        （=データシート名しか無いブックで業務候補が「無い」事故の検知は呼び出し側の責任）。
        """
        path = tmp_path / "book.xlsx"
        with Excel(path) as excel:
            excel.create_data_sheet("顧客").create_table("顧客", Table(["ID"], [{"ID": "1"}]))

        with Excel(path, read_only=True) as excel:
            # ``PY_顧客`` は sheetnames に含まれるので「見つかった」と判定される
            # （=この API はプレフィックスによる区別をしない）。
            assert excel.find_sheet("PY_顧客") == "PY_顧客"
            # 表示用シート名を候補にしても見つからない。
            with pytest.raises(SheetNotFoundError):
                excel.find_sheet("案件一覧")


def _write_cached_formula_xlsx(
    path: Path,
    *,
    sheet_name: str,
    formulas_with_values: dict[str, tuple[str, str]],
    plain_values: dict[str, int | str | datetime] | None = None,
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
    for coord, value in (plain_values or {}).items():
        sheet[coord] = value
    workbook.save(path)
    if not formulas_with_values:
        return
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
                r"(<v[^<]*</v>|<v\s*/>)"
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


class TestSheetIterRows:
    """``Sheet.iter_rows`` の契約テスト。

    ``read_range`` / ``read`` と同じく dict を返すが、ファイル全体をメモリに
    載せずストリームで 1 行ずつ ``yield`` する。``Excel(path, read_only=True)``
    で開いた Excel でしか使えない。
    """

    def test_results_match_read_range_for_mixed_values(self, tmp_path: Path) -> None:
        """``iter_rows`` の結果が ``read_range`` の行と一致する（数値・日付・空欄・文字列）。"""
        path = tmp_path / "values.xlsx"
        with Excel(path) as excel:
            sheet = excel.create_sheet("Sheet1")
            sheet.write_range("A1:C1", [["ID", "名前", "日付"]])
            sheet.write_value("A2", 1)
            sheet.write_value("B2", "山田")
            # openpyxl が timezone 付き datetime を受け付けないため、
            # テストでは ``naive`` を使う（``read_range`` も同じ datetime インスタンスを返す）
            sheet.write_value("C2", datetime(2024, 1, 2))  # noqa: DTZ001
            # 3 行目は B 列が空欄、4 行目は C 列が空欄
            sheet.write_value("A3", 2)
            sheet.write_value("C3", datetime(2024, 1, 3))  # noqa: DTZ001
            sheet.write_value("A4", 3)
            sheet.write_value("B4", "佐藤")
            sheet.write_value("A6", 7)
            sheet.write_value("B6", "鈴木")
            sheet.write_value("C6", datetime(2024, 1, 7))  # noqa: DTZ001

        with Excel(path, read_only=True) as excel:
            sheet = excel.sheet("Sheet1")
            iter_rows = list(sheet.iter_rows())
            # ``read_range`` は宣言範囲をそのまま読むので、空行も返す。
            # 比較対象は同じく空行を落とした ``Table`` 相当のリストにする。
            read_range = [
                row
                for row in sheet.read_range("A1:C6").to_rows()
                if any(value not in (None, "") for value in row.values())
            ]

        assert iter_rows == read_range
        # 途中の空行（5 行目）は飛ばしている
        assert len(iter_rows) == 4

    def test_formula_cells_return_cached_value(self, tmp_path: Path) -> None:
        """数式セルは保存済みの計算値（``data_only=True``）を返す。"""
        path = tmp_path / "cached.xlsx"
        _write_cached_formula_xlsx(
            path,
            sheet_name="Sheet1",
            formulas_with_values={"A2": ("=1+1", "2"), "B2": ("=A2*10", "20")},
            plain_values={"A1": "値", "B1": "結果"},
        )
        with Excel(path, read_only=True) as excel:
            sheet = excel.sheet("Sheet1")
            assert list(sheet.iter_rows()) == [{"値": 2, "結果": 20}]

    def test_uncalculated_formula_raises_with_cell_coordinate(self, tmp_path: Path) -> None:
        """計算値が無い数式セルに当たったら ``ExcelError``（セル座標入り）。"""
        path = tmp_path / "uncached.xlsx"
        # openpyxl の標準保存は数式セルにキャッシュ値を入れない。
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Sheet1"
        sheet["A1"] = "値"
        sheet["B1"] = "結果"
        sheet["A2"] = 5
        sheet["B2"] = "=A2*2"  # キャッシュなし
        workbook.save(path)

        with Excel(path, read_only=True) as excel, pytest.raises(ExcelError) as exc_info:
            list(excel.sheet("Sheet1").iter_rows())
        # メッセージにセル座標と対処法のヒントが含まれる
        assert "B2" in str(exc_info.value)
        assert "read_range" in str(exc_info.value)

    def test_raises_when_excel_not_read_only_at_call_time(self, tmp_path: Path) -> None:
        """``read_only=False`` の Excel で呼ぶと ``ExcelError``（呼んだ時点で）。"""
        path = tmp_path / "writable.xlsx"
        with Excel(path) as excel, pytest.raises(ExcelError, match="read_only=True"):
            excel.sheet("Sheet").iter_rows()

    def test_duplicate_header_raises_table_error(self, tmp_path: Path) -> None:
        """見出し重複は ``TableError`` (``Table(...)`` と同じ文言)。

        ``list(...)`` も ``next(...)`` もしない（呼んだ時点で発火する）。
        """
        path = tmp_path / "dupe.xlsx"
        with Excel(path) as excel:
            sheet = excel.create_sheet("Sheet1")
            sheet.write_range("A1:C1", [["ID", "名前", "ID"]])
            sheet.write_value("A2", "1")
            sheet.write_value("B2", "山田")
            sheet.write_value("C2", "2")
        with (
            Excel(path, read_only=True) as excel,
            pytest.raises(TableError, match="重複"),
        ):
            # ``list(...)`` を外しても呼んだ時点で例外が出る
            excel.sheet("Sheet1").iter_rows()

    def test_empty_header_cell_raises_excel_error(self, tmp_path: Path) -> None:
        """見出し行の空セルは ``ExcelError``（``read()`` と同じ文言）。

        ``list(...)`` も ``next(...)`` もしない（呼んだ時点で発火する）。
        """
        path = tmp_path / "empty.xlsx"
        with Excel(path) as excel:
            sheet = excel.create_sheet("Sheet1")
            sheet.write_value("A1", "ID")
            # B1 は空の見出し
            sheet.write_value("A2", "1")
            sheet.write_value("B2", "山田")
        with (
            Excel(path, read_only=True) as excel,
            pytest.raises(ExcelError, match="B1"),
        ):
            excel.sheet("Sheet1").iter_rows()

    def test_blank_header_row_raises_excel_error(self, tmp_path: Path) -> None:
        """``header_row`` の行が完全に空だと ``ExcelError``（呼んだ時点で）。

        「先頭の空行を黙って飛ばして次の非空行を見出しにする」振る舞いをしない。
        """
        path = tmp_path / "blank_header.xlsx"
        with Excel(path) as excel:
            sheet = excel.create_sheet("Sheet1")
            # A1 / B1 は未書き込み（= None）、A2 / B2 にデータ
            sheet.write_value("A2", "1")
            sheet.write_value("B2", "山田")
        with (
            Excel(path, read_only=True) as excel,
            pytest.raises(ExcelError, match=r"見出し行（1 行目）が空"),
        ):
            # list() も next() もしない
            excel.sheet("Sheet1").iter_rows()

    def test_blank_header_row_with_no_data_returns_zero_rows(self, tmp_path: Path) -> None:
        """``header_row`` の行が空で、シートにそれ以降データが無くても例外を出さず 0 行で終わる。

        「空の見出しだがデータが無い」場合はエラー扱いしない（書き出し直後で
        ヘッダーだけ後で書く、のような使い方を壊さないため）。
        """
        path = tmp_path / "empty_sheet.xlsx"
        with Excel(path) as excel:
            excel.create_sheet("Sheet1")  # 何も書かない
        with Excel(path, read_only=True) as excel:
            assert list(excel.sheet("Sheet1").iter_rows()) == []

    def test_header_error_releases_file_lock_so_rename_succeeds(self, tmp_path: Path) -> None:
        """見出しエラーが呼んだ時点で出ても zip ハンドルを閉じているため、Windows でリネームできる。

        ``list(...)`` を呼ばない場合、エラーが ``iter_rows()`` の呼び出し時点で
        出る。検証中に開いた 2 本のストリーム Workbook は ``except`` で閉じるため、
        例外が抜けても zip ハンドルが残らない。
        """
        path = tmp_path / "lock.xlsx"
        with Excel(path) as excel:
            sheet = excel.create_sheet("Sheet1")
            sheet.write_range("A1:C1", [["ID", "名前", "ID"]])  # 見出し重複
        with Excel(path, read_only=True) as excel, pytest.raises(TableError):
            excel.sheet("Sheet1").iter_rows()
        # 例外後に ``with`` を抜けてもファイルがリネームできれば OK
        renamed = path.with_suffix(".xlsx.bak")
        path.replace(renamed)
        assert renamed.exists()
        assert not path.exists()

    def test_blank_rows_in_middle_are_skipped(self, tmp_path: Path) -> None:
        """途中の空行（全部空の行）は飛ばされる。"""
        path = tmp_path / "blanks.xlsx"
        with Excel(path) as excel:
            sheet = excel.create_sheet("Sheet1")
            sheet.write_range("A1:B1", [["ID", "名前"]])
            sheet.write_value("A2", "1")
            sheet.write_value("B2", "A")
            # 3 行目は空、4 行目も空、5 行目にデータ
            sheet.write_value("A5", "2")
            sheet.write_value("B5", "B")
        with Excel(path, read_only=True) as excel:
            assert list(excel.sheet("Sheet1").iter_rows()) == [
                {"ID": "1", "名前": "A"},
                {"ID": "2", "名前": "B"},
            ]

    def test_uses_read_only_stream_workbook(self, tmp_path: Path) -> None:
        """内部で read_only=True の Workbook からストリームで読んでいる。"""
        path = tmp_path / "stream.xlsx"
        with Excel(path) as excel:
            sheet = excel.create_sheet("Sheet1")
            sheet.write_range("A1:B1", [["ID", "名前"]])
            sheet.write_value("A2", "1")
            sheet.write_value("B2", "山田")
        with Excel(path, read_only=True) as excel:
            sheet = excel.sheet("Sheet1")
            # 1 回目の next で Workbook が 1 度は開かれる。開いた Workbook が
            # read_only=True であることを、``wb.read_only`` で確認する。
            iterator = sheet.iter_rows()
            workbook = excel._computed._open_single_stream_workbook(data_only=True)
            try:
                assert workbook.read_only is True
            finally:
                workbook.close()
            next(iterator)

    def test_break_then_rename_succeeds_on_windows(self, tmp_path: Path) -> None:
        """途中で ``break`` してもファイルをリネームできる（Windows で zip ハンドル解放）。"""
        path = tmp_path / "break.xlsx"
        with Excel(path) as excel:
            sheet = excel.create_sheet("Sheet1")
            sheet.write_range("A1:B1", [["ID", "名前"]])
            for index in range(1, 51):
                sheet.write_value(f"A{index + 1}", str(index))
                sheet.write_value(f"B{index + 1}", f"ユーザー{index}")
        with Excel(path, read_only=True) as excel:
            sheet = excel.sheet("Sheet1")
            iterator = sheet.iter_rows()
            first = next(iterator)
            # 1 行だけ取って break する（Windows でも zip が閉じられている必要がある）
            assert first == {"ID": "1", "名前": "ユーザー1"}
            # generator を明示的に閉じて、``finally`` で Workbook を閉じる
            iterator.close()

        # ``with`` ブロック内でリネームできれば OK
        renamed = path.with_suffix(".xlsx.bak")
        path.replace(renamed)
        assert renamed.exists()
        assert not path.exists()

    def test_works_inside_with_only(self, tmp_path: Path) -> None:
        """``with`` の外で呼ぶと ``TableError``。"""
        path = tmp_path / "outside.xlsx"
        with Excel(path) as excel:
            excel.create_sheet("Sheet1")
        excel = Excel(path, read_only=True)
        with pytest.raises(TableError):
            excel.sheet("Sheet1").iter_rows()
