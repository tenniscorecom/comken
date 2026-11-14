"""引用符付きのパス（Windows の「パスのコピー」の形）を開けることのテスト。

``"C:\\作業\\data.csv"`` のように引用符付きで貼り付けられると、引用符が
残ったまま「対応していないファイル形式です」になる。引用符を外してから
``Path`` にするので、その引用符つきの文字列でも開けて読める。
"""

from pathlib import Path

from comken.core.files.base import FileBase
from comken.toolbox.csv import CSV
from comken.toolbox.excel import Excel


def _quoted(path: Path) -> str:
    """パスを引用符付きの文字列にする（Windows の「パスのコピー」の形）。"""
    return f'"{path}"'


def test_csv_accepts_quoted_path_and_strips_quotes(tmp_path: Path) -> None:
    """引用符付きの文字列パスで CSV が開けて読める。"""
    path = tmp_path / "data.csv"
    path.write_text("ID,名前\n001,山田\n", encoding="utf-8")

    with CSV(_quoted(path)) as csv_file:
        table = csv_file.read()

    assert table.to_rows() == [{"ID": "001", "名前": "山田"}]
    assert csv_file.path == path
    assert '"' not in str(csv_file.path)


def test_excel_accepts_quoted_path_and_strips_quotes(tmp_path: Path) -> None:
    """引用符付きの文字列パスで Excel が開けて読める。"""
    path = tmp_path / "book.xlsx"
    with Excel(path) as excel:
        excel.create_data_sheet("顧客")

    with Excel(_quoted(path), read_only=True) as excel:
        assert excel.list_sheets() == ["Sheet", "PY_顧客"]
        assert excel.path == path
        assert '"' not in str(excel.path)


def test_file_base_accepts_quoted_path(tmp_path: Path) -> None:
    """FileBase も引用符付きの文字列パスを受ける。"""
    path = tmp_path / "data.csv"
    path.write_text("ID\n", encoding="utf-8")

    base = FileBase(_quoted(path))

    assert base.path == path
    assert '"' not in str(base.path)


def test_path_object_is_left_untouched(tmp_path: Path) -> None:
    """``Path`` で渡されたものは引用符を剥がさない（引用符は値の一部）。"""
    path = tmp_path / "data.csv"

    assert CSV(path).path == path
    assert FileBase(path).path == path


def test_unbalanced_quotes_are_left_untouched(tmp_path: Path) -> None:
    """引用符が対になっていない値はそのままにする。"""
    unbalanced = '"C:\\作業\\data.csv'

    assert CSV(unbalanced).path == Path(unbalanced)
