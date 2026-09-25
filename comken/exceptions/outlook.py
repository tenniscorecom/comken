"""comken/exceptions/outlook.py — Outlook 操作の例外。"""

from comken.exceptions.base import ComkenError


class OutlookError(ComkenError):
    """Outlook 関連エラーの分類。具体的な状況はメッセージに出る

    対処:
        メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ
    """
