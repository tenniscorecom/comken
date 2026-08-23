"""comken/internal/exceptions.py — 社内ライブラリ呼び出しの共通例外。"""

from comken.exceptions import ComkenError


class InternalLibraryError(ComkenError):
    """社内ライブラリの呼び出しに失敗したときの基底例外。"""


class InternalLibraryNotFoundError(InternalLibraryError):
    """指定した社内ライブラリが見つからない場合。"""

    def __init__(self, library_name: str) -> None:
        self.library_name = library_name
        super().__init__(
            f"社内ライブラリ {library_name!r} が見つかりません。"
            "社内 LAN 環境から、共有サーバ上の PYTHONPATH が通っているか確認してください。"
        )


class InternalLibraryVersionMismatchError(InternalLibraryError):
    """指定したバージョンの社内ライブラリが見つからない場合。"""

    def __init__(self, library_name: str, required_version: str) -> None:
        self.library_name = library_name
        self.required_version = required_version
        super().__init__(
            f"社内ライブラリ {library_name!r} のバージョン {required_version!r} が"
            "見つかりません。"
        )
