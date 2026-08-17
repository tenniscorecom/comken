"""comken/exceptions/rpa.py — 社内 RPA 基盤の呼び出しに関する例外。"""

from comken.exceptions.base import ComkenError


class RpaError(ComkenError):
    """社内 RPA 基盤の呼び出しに関するエラー

    対処:
        画面に表示された具体的なエラー名を上の表から探す
    """


class RpaLibraryNotFoundError(RpaError):
    """社内ライブラリを読み込めない

    発生箇所: comken.toolbox.rpa.backoffice() / comken.toolbox.rpa.intranet()

    対処:
        実行.bat の PYTHONPATH に社内ライブラリが入っているか確認する。
        バージョンが変わった場合は管理者へ連絡する
    """

    def __init__(self, module_path: str, detail: Exception) -> None:
        super().__init__(
            f"社内ライブラリを読み込めませんでした: {module_path}\n"
            f"（{detail}）\n"
            "社内ライブラリが PYTHONPATH に含まれているか、"
            "comken/toolbox/rpa.py の import 行が今の社内ライブラリ名・バージョンと"
            "合っているか確認してください。"
        )
