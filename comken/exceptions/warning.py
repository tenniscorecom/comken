"""comken/exceptions/warning.py — 型変換時に使う警告。"""

import warnings
from collections.abc import Callable
from typing import Any, TypeVar, cast

_T = TypeVar("_T")


class _Warnings:
    """ライブラリが発行する UserWarning のメッセージ。"""

    COERCION = "{param} に {type_name}（{value!r}）が渡されました。{expected} に変換します。"


def _callable_ctor(t: type[_T]) -> Callable[[Any], _T]:
    """``type[_T]`` を ``Callable[[Any], _T]`` として読み替える内部ヘルパー。

    pyright は ``type[_T]`` だけでは ``_T`` のコンストラクタ引数を推論できないため、
    シグネチャ付きの callable として教えて呼び出し可能にする。実行時は ``t(value)`` と
    等価（``type`` のインスタンスは呼び出せる）。
    """
    return cast(Callable[[Any], _T], t)


def _warn_coerce(value: Any, expected: type[_T], param: str, stacklevel: int = 3) -> _T:
    """型が違う場合に警告して変換する。"""
    if value is None:
        raise TypeError(f"{param} に None が渡されました。{expected.__name__} を渡してください。")
    if not isinstance(value, expected):
        warnings.warn(
            _Warnings.COERCION.format(
                param=param,
                type_name=type(value).__name__,
                value=value,
                expected=expected.__name__,
            ),
            UserWarning,
            stacklevel=stacklevel,
        )
    # expected は呼び出し側で ``str`` / ``int`` などの具体型を渡されるため、
    # 実行時は ``expected(value)`` で安全に変換できる。pyright は ``type[_T]`` だけでは
    # ``_T`` のコンストラクタ引数シグネチャを推論できないため、callable 型へ局所キャストして
    # シグネチャを教える（型レベルだけで Any には逃げない）
    return cast(_T, _callable_ctor(expected)(value))
