"""v1.0.0 で統合した旧例外名の別名機構（``FutureWarning`` 付き）を検証する。

旧名を ``from comken.exceptions import OldName`` / ``comken.exceptions.OldName``
で参照すると、新クラスが返り ``FutureWarning`` が出る。会社側プロジェクトは
``grep`` できないため、無警告で壊すと現場のコードがサイレントに止まる。

**壊れたら落ちる**: ``__getattr__`` を削除して ``test_old_name_resolves_with_future_warning``
が落ちれば、別名機構が壊れていることを CI で検出できる。
"""

from __future__ import annotations

import warnings

import pytest

import comken.exceptions
from comken.exceptions import ComkenFileNotFoundError

# 別名テーブルは ``comken/exceptions/__init__.py`` の ``_RENAMED_EXCEPTIONS`` と
# 同じ 8 件。テスト側で再記述しているのは、 ``__init__.py`` 側を ``pop`` された
# ときに「**登録漏れを CI で検出する**」ため。``__getattr__`` を消して
# ``getattr(comken.exceptions, name)`` が ``AttributeError`` になれば落ちる。
_OLD_TO_NEW_NAMES: dict[str, type[ComkenFileNotFoundError]] = {
    "ExcelFileNotFoundError": ComkenFileNotFoundError,
    "CSVFileNotFoundError": ComkenFileNotFoundError,
    "AccessFileNotFoundError": ComkenFileNotFoundError,
    "ConfigFileNotFoundError": ComkenFileNotFoundError,
    "DataLoaderLauncherNotFoundError": ComkenFileNotFoundError,
    "DataLoaderResultFileMissingError": ComkenFileNotFoundError,
    "OutlookAttachmentNotFoundError": ComkenFileNotFoundError,
    "ReportFolderNotFoundError": ComkenFileNotFoundError,
}


@pytest.mark.parametrize(
    ("old_name", "new_cls"),
    list(_OLD_TO_NEW_NAMES.items()),
)
def test_old_name_resolves_with_future_warning(
    old_name: str,
    new_cls: type[ComkenFileNotFoundError],
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
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        old_cls = getattr(comken.exceptions, old_name)

    try:
        raise ComkenFileNotFoundError("テスト用", "dummy/path")
    except old_cls:
        return  # 捕捉できた場合はここで終了
    pytest.fail(f"{old_name} で ComkenFileNotFoundError を捕捉できなかった")


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


def test_old_name_module_is_not_imported_via_attribute_path() -> None:
    """``comken.exceptions.<旧サブモジュール>.<旧例外>`` は対象外であることを確認する。

    別名機構は **パッケージ入口からの import / 属性アクセスだけ**を救う設計。
    旧サブモジュール経由は対象外だが、 その境界が崩れていないか（うっかり
    サブモジュール側に旧クラスを残していないか）の最低限のチェックとして、
    「旧サブモジュールから旧名を取り出すと想定どおり失敗する」ことを確認する。
    """
    import comken.exceptions.excel as excel_module

    # ``comken.exceptions.excel.ExcelFileNotFoundError`` は今存在しないはず。
    with pytest.raises(AttributeError):
        excel_module.ExcelFileNotFoundError  # noqa: B018
