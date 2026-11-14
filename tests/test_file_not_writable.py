"""保存先を開いたまま保存したときのエラー（FileNotWritableError）のテスト。

Excel などでファイルを開いたまま comken が保存すると、置き換えが
``PermissionError: [WinError 5]`` になり、一時ファイル名だけが利用者へ
出てしまう。ここでは、その症状を comken の例外へ変換していることを
実ファイルで確認する（実ファイルを使うので、置き場所も中身も実物）。
"""

from pathlib import Path

import pytest

from comken.exceptions import FileNotWritableError
from comken.toolbox.csv import CSV
from comken.toolbox.excel import Excel


def _hold_open(path: Path):
    """保存先を開いたままにする（Windows では置き換えが失敗する）。"""
    return path.open("r+b")


def _temp_files(directory: Path) -> list[Path]:
    """atomic_write の一時ファイル（``~`` 始まり）を集める。"""
    return sorted(p for p in directory.iterdir() if p.name.startswith("~"))


def test_csv_save_reports_file_not_writable(tmp_path: Path) -> None:
    """CSV の保存先が他で開かれていると FileNotWritableError になる。"""
    path = tmp_path / "data.csv"
    path.write_text("ID,名前\n001,山田\n", encoding="utf-8")

    with (
        _hold_open(path),
        pytest.raises(FileNotWritableError),
        CSV(path) as csv_file,
    ):
        csv_file.replace([{"ID": "002", "名前": "鈴木"}])


def test_excel_save_reports_file_not_writable(tmp_path: Path) -> None:
    """Excel の保存先が他で開かれていると FileNotWritableError になる。"""
    path = tmp_path / "book.xlsx"
    with Excel(path) as excel:
        excel.create_data_sheet("顧客")

    with (
        _hold_open(path),
        pytest.raises(FileNotWritableError),
        Excel(path) as excel,
    ):
        excel.create_data_sheet("得意先")


def test_message_shows_target_path_not_temp_file(tmp_path: Path) -> None:
    """メッセージには保存先のパスが出て、一時ファイル名は出ない。"""
    path = tmp_path / "data.csv"
    path.write_text("ID,名前\n001,山田\n", encoding="utf-8")

    with (
        _hold_open(path),
        pytest.raises(FileNotWritableError) as caught,
        CSV(path) as csv_file,
    ):
        csv_file.replace([{"ID": "002", "名前": "鈴木"}])

    message = str(caught.value)
    assert str(path) in message
    assert "~" not in message


def test_target_content_is_kept(tmp_path: Path) -> None:
    """保存に失敗しても、元のファイルの中身は変わらない。"""
    path = tmp_path / "data.csv"
    original = "ID,名前\n001,山田\n"
    path.write_text(original, encoding="utf-8")

    with (
        _hold_open(path),
        pytest.raises(FileNotWritableError),
        CSV(path) as csv_file,
    ):
        csv_file.replace([{"ID": "002", "名前": "鈴木"}])

    assert path.read_text(encoding="utf-8") == original


def test_no_temp_file_is_left(tmp_path: Path) -> None:
    """保存に失敗しても、一時ファイルは残らない。"""
    path = tmp_path / "data.csv"
    path.write_text("ID,名前\n001,山田\n", encoding="utf-8")

    with (
        _hold_open(path),
        pytest.raises(FileNotWritableError),
        CSV(path) as csv_file,
    ):
        csv_file.replace([{"ID": "002", "名前": "鈴木"}])

    assert _temp_files(tmp_path) == []


def test_permission_error_handler_still_catches(tmp_path: Path) -> None:
    """``except PermissionError`` で受ける既存のコードはそのまま動く。"""
    path = tmp_path / "data.csv"
    path.write_text("ID,名前\n001,山田\n", encoding="utf-8")

    with (
        _hold_open(path),
        pytest.raises(PermissionError),
        CSV(path) as csv_file,
    ):
        csv_file.replace([{"ID": "002", "名前": "鈴木"}])
