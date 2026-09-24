"""tests/_table_getitem_typecheck.py — ``Table.__getitem__`` の型回帰防止。

``Table.__getitem__`` の ``@overload`` が機能していることを pyright で
確認するための小さなモジュール。実行はしない（pytest に登録しない）。
``table[0]["列"]`` が ``dict[str, Any]`` を返し、
``table[1:][0]["列"]`` が ``list[dict[str, Any]]`` を返すことだけを確認する。

オーバーロードを外して ``dict[str, Any] | list[dict[str, Any]]`` の合成型
に戻すと、このモジュールは pyright でエラーを出す（戻り値の型が確定
しないため ``["列"]`` のアクセスや ``.append`` が失敗する）。
"""

from comken.core.table import Table


def _int_index_returns_dict() -> dict[str, str]:
    """``table[0]`` が ``dict[str, Any]`` を返すこと。"""
    table = Table(["id", "value"], [{"id": "a", "value": "1"}])
    row = table[0]
    # ``row`` が ``dict[str, Any]`` 確定なら ``row["id"]`` は Any → str 代入可
    return {"got": row["id"]}


def _slice_returns_list_of_dict() -> list[str]:
    """``table[1:]`` が ``list[dict[str, Any]]`` を返すこと。"""
    table = Table(["id", "value"], [{"id": "a", "value": "1"}, {"id": "b", "value": "2"}])
    rows = table[1:]
    # ``rows`` が ``list[dict[str, Any]]`` 確定なら要素の ``["id"]`` は Any → str 代入可
    return [row["id"] for row in rows]
