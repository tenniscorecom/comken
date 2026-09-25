"""comken/exceptions/state.py — 状態ファイルに関する例外。"""

from comken.exceptions.base import ComkenError


class StateError(ComkenError):
    """state.ini に関するエラー。具体的な状況はメッセージに出る

    対処:
        メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ
    """
