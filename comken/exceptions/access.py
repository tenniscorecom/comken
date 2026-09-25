"""comken/exceptions/access.py — Microsoft Access 操作に関する例外。"""

from comken.exceptions.base import ComkenError


class AccessError(ComkenError):
    """Access に関するエラー。具体的な状況はメッセージに出る

    対処:
        メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ
    """
