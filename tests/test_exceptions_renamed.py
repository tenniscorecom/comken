"""v1.0.0 で統合した旧例外名の別名機構（``FutureWarning`` 付き）を検証する。

旧名を ``from comken.exceptions import OldName`` / ``comken.exceptions.OldName``
で参照すると、新クラスが返り ``FutureWarning`` が出る。会社側プロジェクトは
``grep`` できないため、無警告で壊すと現場のコードがサイレントに止まる。

対応表は ``comken/exceptions/__init__.py`` の ``_RENAMED_EXCEPTIONS`` に
一元化されている。テスト側では再記述せず、その dict を直接 parametrize に
回す（``__init__.py`` 側を ``pop`` されたときの登録漏れ検出も兼ねる）。

**壊れたら落ちる**: ``__getattr__`` を削除して ``test_old_name_resolves_with_future_warning``
が落ちれば、別名機構が壊れていることを CI で検出できる。
"""

from __future__ import annotations

import warnings

import pytest

import comken.exceptions
from comken.exceptions import ComkenError

_OLD_TO_NEW_NAMES: dict[str, type[ComkenError]] = {
    old_name: getattr(comken.exceptions, new_name)
    for old_name, new_name in comken.exceptions._RENAMED_EXCEPTIONS.items()
}


@pytest.mark.parametrize(
    ("old_name", "new_cls"),
    list(_OLD_TO_NEW_NAMES.items()),
)
def test_old_name_resolves_with_future_warning(
    old_name: str,
    new_cls: type[ComkenError],
) -> None:
    """旧名を取り出すと ``FutureWarning`` が出て新クラスと同一。

    ``__getattr__`` を消すと ``getattr`` が ``AttributeError`` になり落ちる。
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        resolved = getattr(comken.exceptions, old_name)

    assert resolved is new_cls, f"{old_name}: 新クラスと同一ではない（{resolved} is not {new_cls}）"
    future_warnings = [w for w in caught if issubclass(w.category, FutureWarning)]
    assert len(future_warnings) == 1, (
        f"{old_name}: FutureWarning が想定通りに1件出ない（{len(future_warnings)} 件）"
    )
    message = str(future_warnings[0].message)
    assert old_name in message, f"{old_name}: 警告メッセージに旧名が含まれていない: {message}"
    assert new_cls.__name__ in message, (
        f"{old_name}: 警告メッセージに新クラス名が含まれていない: {message}"
    )


@pytest.mark.parametrize("old_name", list(_OLD_TO_NEW_NAMES))
def test_except_old_name_catches_new_class(old_name: str) -> None:
    """``except OldName:`` ブロックに新クラスの例外が流れる。

    旧名は ``__getattr__`` 経由でしか取れないので、 ``except`` 文で使うときに
    警告が出ないよう、 ここでは抑制する（**捕捉できることが本質**なので、
    警告の件数をテストする関心事は上のテストに分離してある）。

    各新クラスのコンストラクタの形が違うので、 ``Exception.__new__`` で
    インスタンスを作って ``args`` を直接設定する（``raise`` 直前で十分）。
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        old_cls = getattr(comken.exceptions, old_name)
        new_cls = _OLD_TO_NEW_NAMES[old_name]

    # 統合先クラスごとにコンストラクタの引数形が違うため、
    # ``Exception`` 流の ``__new__`` でインスタンス化し ``args`` を直接渡す。
    instance = new_cls.__new__(new_cls)
    instance.args = ("テスト用",)
    try:
        raise instance
    except old_cls:
        return  # 捕捉できた場合はここで終了
    pytest.fail(f"{old_name} で新クラスを捕捉できなかった")


def test_unknown_name_raises_attribute_error() -> None:
    """登録されていない名前は ``AttributeError``。

    別名機構が「**すべてを返す**」実装に退化していないことを担保する。
    """
    with pytest.raises(AttributeError):
        comken.exceptions.DefinitelyNotAExceptionName_123  # noqa: B018


def test_old_names_are_not_in_all() -> None:
    """旧名は ``__all__`` に入っていない。

    ``__all__`` ベースのドキュメント生成（``docs/ERRORS.md`` /
    ``docs/自動生成/API.md``）が旧名を再公開しないようにする。
    """
    leaked = [name for name in _OLD_TO_NEW_NAMES if name in comken.exceptions.__all__]
    assert not leaked, f"旧名が __all__ に残っている: {leaked}"
