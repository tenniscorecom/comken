"""社内 RPA 基盤の呼び出しに関する例外。"""

from .base import OriginalLibsError


class RpaError(OriginalLibsError):
    """社内 RPA 基盤の呼び出しに関する例外をまとめて捕捉するための基底クラス。"""


class RpaLibraryNotFoundError(RpaError):
    """社内ライブラリを読み込めない場合。

    発生箇所: comken.run.backoffice() / comken.run.intranet()
    """

    def __init__(self, module_path: str, detail: Exception) -> None:
        super().__init__(
            f"社内ライブラリを読み込めませんでした: {module_path}\n"
            f"（{detail}）\n"
            "社内ライブラリが PYTHONPATH に含まれているか、"
            "comken/run.py の import 行が今の社内ライブラリ名・バージョンと"
            "合っているか確認してください。"
        )
