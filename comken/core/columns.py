"""comken/core/columns.py — Excel の列記号（A, B, AA…）と列番号の相互変換（CSV でも使う）"""

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


def num_to_col(number: int) -> str:
    """列番号を Excel の列レターに変換する（1→A, 2→B, 27→AA）。``col_to_num`` の逆。

    ``f"{num_to_col(5)}{row}"`` のようにセル番地を組み立てるときに使う。

    Args:
        number: 1始まりの列番号。

    Returns:
        大文字の列レター。

    Raises:
        InvalidColumnError: 1 未満、または整数でない場合（``bool`` も含む）。
    """
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        raise InvalidColumnError(number)
    letters = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def column_number(col: int | str) -> int:
    """列番号または列記号を1始まりの列番号に揃える。"""
    return col_to_num(col) if isinstance(col, str) else int(col)
