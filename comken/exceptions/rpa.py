"""comken/exceptions/rpa.py — 旧 RpaError の後方互換用シム。

実体は ``comken.internal.exceptions.InternalLibraryError`` に移動済み。
旧名称で import しているコードは DeprecationWarning が出るが、引き続き動く。

    # 旧（動くが DeprecationWarning が出る）
    from comken.exceptions.rpa import RpaError, RpaLibraryNotFoundError

    # 新
    from comken.internal.exceptions import (
        InternalLibraryError,
        InternalLibraryNotFoundError,
    )
"""

import warnings

from comken.internal.exceptions import (
    InternalLibraryError,
    InternalLibraryNotFoundError,
    InternalLibraryVersionMismatchError,
)

warnings.warn(
    "RpaError / RpaLibraryNotFoundError は comken.internal.exceptions に移動しました。"
    "新名称を使用してください。",
    DeprecationWarning,
    stacklevel=2,
)


# 後方互換用エイリアス。
# クラスとして再定義し、明示的な docstring を持たせる
# （エイリアスだけだと InternalLibraryError.__doc__ を介在して
#  PowerShell のコードページで読まれるため、ERRORS.md 自動生成が壊れる）。
class RpaError(InternalLibraryError):
    """旧 RpaError の後方互換シム。

    実体は ``comken.internal.exceptions.InternalLibraryError``。
    対処:
        社内 LAN 環境から、共有サーバ上の PYTHONPATH が通っているか確認し、
        指定したライブラリ名のフォルダが存在するか確かめる。
    """


class RpaLibraryNotFoundError(InternalLibraryNotFoundError):
    """旧 RpaLibraryNotFoundError の後方互換シム。

    実体は ``comken.internal.exceptions.InternalLibraryNotFoundError``。
    対処:
        社内 LAN 環境から、共有サーバ上の PYTHONPATH が通っているか確認し、
        指定したライブラリ名のフォルダが存在するか確かめる。
    """


class RpaLibraryVersionMismatchError(InternalLibraryVersionMismatchError):
    """旧 RpaLibraryVersionMismatchError の後方互換シム。

    実体は ``comken.internal.exceptions.InternalLibraryVersionMismatchError``。
    対処:
        共有サーバ上の対象ライブラリのバージョンを確認し、
        呼び出し側の指定と一致しているか確かめる。
    """
