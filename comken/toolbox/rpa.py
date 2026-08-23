"""comken/toolbox/rpa.py — 社内 RPA 呼び出しの互換シム。

実体は ``comken.internal.rpa`` に移動済み。旧パスから import しても
動くが、**名前を取り出した瞬間に FutureWarning** が出る。
``import comken`` や ``import comken.exceptions`` だけでは警告しない。

    # 旧（動くが警告が出る）
    from comken.toolbox.rpa import backoffice, intranet

    # 新（推奨）
    from comken.internal.rpa import backoffice, intranet
"""

import warnings

from comken.internal import rpa as _rpa

# 旧パスを経由して名前を取り出したときだけ警告を出す。
# ``import comken`` 単体では出さない（利用者コードに伝播しない）。
_WARN_MESSAGE = (
    "comken.toolbox.rpa は comken.internal.rpa に移動しました。"
    "新パス（comken.internal.rpa）から import してください。"
)


def __getattr__(name: str) -> object:
    """旧パスからの属性アクセスを検知して ``FutureWarning`` を出す。"""
    if name in {"backoffice", "intranet", "RPA_LIBRARY_NAME"}:
        warnings.warn(
            _WARN_MESSAGE,
            FutureWarning,
            stacklevel=2,
        )
        return getattr(_rpa, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# `__getattr__` で遅延解決する名前を `__all__` に列挙する（モジュール読込時に属性は未定義）
__all__ = ["backoffice", "intranet", "RPA_LIBRARY_NAME"]  # noqa: F822
