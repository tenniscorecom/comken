"""``print(table)`` で表の中身を見えるようにする機能のテスト。

``repr()`` は1行で規模と列名を示し、``str()``（``print`` の表示）は
列名を並べた上で先頭10行を全角・半角の幅をそろえて見せる。
"""

import unicodedata

from comken.core.table import Table


def _display_width(text: str) -> int:
    """文字列の表示幅（全角・全角ambig・半角ambig は 2、他は 1）を返す。"""
    return sum(2 if unicodedata.east_asian_width(char) in ("W", "F", "A") else 1 for char in text)


def test_repr_shows_row_count_and_columns() -> None:
    """``repr()`` は1行で「行数 × 列数: 列名」を示す。"""
    table = Table(["ID", "名前"], [{"ID": "001", "名前": "山田"}])

    assert repr(table) == "Table(1行 × 2列: ['ID', '名前'])"


def test_repr_shows_empty_table() -> None:
    """0行の表でも1行で示す。"""
    assert repr(Table(["ID"], [])) == "Table(0行 × 1列: ['ID'])"


def test_str_shows_header_and_column_names() -> None:
    """1行目に規模、その下に列名と値を出す。"""
    table = Table(["ID", "名前"], [{"ID": "001", "名前": "山田"}])

    lines = str(table).splitlines()
    assert lines[0] == "Table 1行 × 2列"
    assert lines[1].startswith("ID")
    assert "名前" in lines[1]
    assert "001" in lines[2]
    assert "山田" in lines[2]


def test_str_aligns_mixed_full_and_half_width_columns() -> None:
    """全角と半角が混じっても、各行の表示幅がそろう。"""
    table = Table(
        ["ID", "名前"],
        [
            {"ID": "001", "名前": "山田"},
            {"ID": "0002", "名前": "鈴木太郎"},
        ],
    )

    body = str(table).splitlines()[1:]
    widths = {_display_width(line) for line in body}
    assert len(widths) == 1, f"行ごとの表示幅がそろっていない: {widths}"


def test_str_shows_remaining_rows_when_over_limit() -> None:
    """10行を超えるときは最後に「… 残り N 行」を出す。"""
    table = Table(["ID"], [{"ID": str(index)} for index in range(11)])

    lines = str(table).splitlines()
    assert lines[-1] == "… 残り 1 行"
    assert len(lines) == 13  # 見出し + 列名 + 10行 + 残り


def test_str_shows_only_header_for_empty_table() -> None:
    """0行のときは列名の行まで出す。"""
    table = Table(["ID", "名前"], [])

    lines = str(table).splitlines()
    assert lines[0] == "Table 0行 × 2列"
    assert len(lines) == 2
    assert "ID" in lines[1]
    assert "名前" in lines[1]


def test_str_truncates_long_cell() -> None:
    """1セルの表示幅が 40 を超えるときは切って「…」を付ける。"""
    table = Table(["メモ"], [{"メモ": "あ" * 60}])

    cell = str(table).splitlines()[2].split(" | ")[0]
    assert cell.endswith("…")
    assert _display_width(cell) == 40


def test_str_shows_newline_as_visible_text() -> None:
    """値の中の改行は表が崩れないよう ``\\n`` として見せる。"""
    table = Table(["メモ"], [{"メモ": "あ\nい"}])

    lines = str(table).splitlines()
    assert len(lines) == 3
    assert "\\n" in lines[2]


def test_str_converts_value_to_string() -> None:
    """値は ``str(value)`` で見せる。"""
    table = Table(["数"], [{"数": 123}])

    assert "123" in str(table).splitlines()[2]
