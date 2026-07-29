"""社内 RPA 基盤の呼び出しに関する例外。"""

from .base import OriginalLibsError


class RpaError(OriginalLibsError):
    """社内 RPA 基盤の呼び出しに関する例外をまとめて捕捉するための基底クラス。"""


class RpaLibraryNotFoundError(RpaError):
    """社内ライブラリを読み込めない場合。

    発生箇所: comken.rpa._load()
    """

    def __init__(self, module_path: str, detail: Exception) -> None:
        super().__init__(
            f"社内ライブラリを読み込めませんでした: {module_path}\n"
            f"（{detail}）\n"
            "社内ライブラリが PYTHONPATH に含まれているか、"
            "comken/rpa.py の LIB_ROOT・LIB_VERSION が今のものと合っているか確認してください。"
        )
