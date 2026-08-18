"""comken/exceptions/warning.py — 型変換時に使う警告。"""

import warnings
from typing import Any, TypeVar, cast

_T = TypeVar("_T")


class _Warnings:
    """ライブラリが発行する UserWarning のメッセージ。"""

    COERCION = "{param} に {type_name}（{value!r}）が渡されました。{expected} に変換します。"


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
    # expected(value) は呼び出し側で型が確定した状態で渡されるため、pyright が「型 _T は
    # 引数を取らない」と誤検知する。実行時は呼び出し側で str/int などの具体型を渡されるため安全
    return cast(_T, expected(value))  # type: ignore[call-arg]
