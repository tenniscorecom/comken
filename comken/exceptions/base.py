"""comken/exceptions/base.py — ライブラリ共通の基底例外。"""


class ComkenError(Exception):
    """comken が出す固有エラー全体

    対処:
        画面に表示された具体的なエラー名を上の表から探す
    """
