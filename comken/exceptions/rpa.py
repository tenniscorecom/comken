"""comken/exceptions/rpa.py — 社内 RPA 基盤呼び出しの共通例外。"""

from comken.exceptions.base import ComkenError


class InternalLibraryError(ComkenError):
    """社内ライブラリの呼び出しに失敗したときの基底例外

    対処:
        画面に表示された具体的なエラー名（NotFound / VersionMismatch）を上の表から探す
    """


class InternalLibraryNotFoundError(InternalLibraryError):
    """指定した社内ライブラリが見つからない

    対処:
        社内 LAN 環境から、共有サーバ上の PYTHONPATH が通っているか確認し、
        指定したライブラリ名のフォルダが存在するか確かめる
    """

    def __init__(self, library_name: str) -> None:
        self.library_name = library_name
        super().__init__(
            f"社内ライブラリ {library_name!r} が見つかりません。"
            "社内 LAN 環境から、共有サーバ上の PYTHONPATH が通っているか確認してください。"
        )


class InternalLibraryVersionMismatchError(InternalLibraryError):
    """指定したバージョンの社内ライブラリが見つからない

    対処:
        共有サーバ上の対象ライブラリのバージョンを確認し、
        呼び出し側の指定と一致しているか確かめる
    """

    def __init__(self, library_name: str, required_version: str) -> None:
        self.library_name = library_name
        self.required_version = required_version
        super().__init__(
            f"社内ライブラリ {library_name!r} のバージョン {required_version!r} が見つかりません。"
        )
