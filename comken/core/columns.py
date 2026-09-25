"""comken/core/columns.py — Excel の列記号（A, B, AA…）と列番号の変換。Excel でも CSV でも使う"""

from comken.exceptions import InvalidColumnError


def col_to_num(letter: str) -> int:
    """Excel の列レターを列番号に変換する（A→1, B→2, AA→27）。

    config.ini に「Q列」のように列レターで書かれた設定を、
    ExcelCOMHandler.read_cell() 等の col 引数（数値）に変換するときに使う。

    Args:
        letter: 列レター（大文字・小文字どちらでも可。A〜Z または AA〜ZZZ 形式）。

    Returns:
        1始まりの列番号。

    Raises:
        InvalidColumnError: 空文字列または半角英字以外が含まれる場合。
    """
    normalized = letter.strip().upper()
    if not normalized or not normalized.isascii() or not normalized.isalpha():
        raise InvalidColumnError(letter)
    result = 0
    for char in normalized:
        result = result * 26 + (ord(char) - ord("A") + 1)
    return result


def column_number(col: int | str) -> int:
    """列番号または列記号を1始まりの列番号に揃える。"""
    return col_to_num(col) if isinstance(col, str) else int(col)
