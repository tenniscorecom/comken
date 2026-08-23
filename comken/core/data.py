"""comken/core/data.py — データ変換・比較ユーティリティ"""

from dataclasses import dataclass

from comken.exceptions import InvalidColumnError, KeyColumnNotFoundError


def col_to_num(letter: str) -> int:
    """Excel の列レターを列番号に変換する（A→1, B→2, AA→27）。

    config.ini に「Q列」のように列レターで書かれた設定を、
    ExcelComHandler.read_cell() 等の col 引数（数値）に変換するときに使う。

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


def diff_row(before: dict, after: dict) -> dict[str, tuple]:
    """1行同士を比較し、値が異なる列だけを {列名: (変更前, 変更後)} で返す。

    CSV の str と Excel の数値は同一視する（"1000" と 1000 は差分にならない）。
    片方にしか存在しない列は、もう片方を空文字（``""``）に揃えて比較する。

    先頭ゼロ付きの文字列（社員番号 "0001" 等）は数値化しない。
    "0001" と 1 は別の値として差分になる（先頭ゼロの消失を検出できる）。
    Args:
        before: 変更前の行（辞書）。
        after: 変更後の行（辞書）。

    Returns:
        {列名: (変更前の値, 変更後の値)} の辞書。値は元の型のまま返す。
    """
    result = {}
    for col in {**before, **after}:
        old, new = before.get(col), after.get(col)
        if _normalize(old) != _normalize(new):
            result[col] = (old, new)
    return result


@dataclass
class RowChange:
    """diff_rows が返す「変更のあった行」の情報。"""

    key: str  # キー列の複合キー（複数列指定時は複合キーとして扱われる）
    before: dict  # 変更前の行全体
    after: dict  # 変更後の行全体
    columns: dict[str, tuple]  # 変わった列だけ {列名: (変更前, 変更後)}


@dataclass
class DiffResult:
    """diff_rows の結果。"""

    added: list[dict]  # after にだけある行
    removed: list[dict]  # before にだけある行
    changed: list[RowChange]  # キーが一致して値が変わった行


def diff_rows(
    before: list[dict],
    after: list[dict],
    key: str,
) -> DiffResult:
    """2つのデータセットをキー列で突合し、差分を返す。

    CSV と Excel をまたいだ比較にも使える（"1000" と 1000 は同一視される）。
    キーが重複する場合は後の行が優先される。
    Args:
        before: 変更前のデータ（辞書のリスト）。
        after: 変更後のデータ（辞書のリスト）。
        key: 行を一意に識別するキー列名。

    Returns:
        DiffResult（added / removed / changed）。

    Raises:
        KeyColumnNotFoundError: key で指定した列が存在しない場合。
    """
    for rows in (before, after):
        if rows and key not in rows[0]:
            raise KeyColumnNotFoundError(key, list(rows[0].keys()))

    before_by_key = {_normalize(row[key]): row for row in before}
    after_by_key = {_normalize(row[key]): row for row in after}

    added = [after_by_key[k] for k in after_by_key if k not in before_by_key]
    removed = [before_by_key[k] for k in before_by_key if k not in after_by_key]
    changed = []
    for k in before_by_key:
        if k not in after_by_key:
            continue
        columns = diff_row(before_by_key[k], after_by_key[k])
        if columns:
            changed.append(
                RowChange(key=k, before=before_by_key[k], after=after_by_key[k], columns=columns)
            )

    return DiffResult(added=added, removed=removed, changed=changed)


def _normalize(value) -> str:
    """比較用に値を文字列へ揃える。

    CSV は全部 str、Excel は int / float / None で返ってくるため、
    そのまま == で比べると「"1000" と 1000」が差分扱いになってしまう。
    None は ""、整数値の float（1000.0）は int（1000）を経由して文字列にする。

    こちらは行の比較用で None を "" に揃える役割を持つ。
    """
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()
