"""Outlook 操作の例外。"""

from pathlib import Path

from .base import ComkenError


class OutlookError(ComkenError):
    """Outlook 関連エラーの基底クラス。"""


class ClassicOutlookNotAvailableError(OutlookError):
    """Classic Outlook を COM で利用できない。"""

    def __init__(self) -> None:
        super().__init__(
            "この PC では従来版（Classic）の Outlook が見つかりません。"
            "新しい Outlook は自動操作に対応していないため、この処理は使えません。"
            "従来版の Outlook を使うか、管理者に相談してください。"
        )


class OutlookFolderNotFoundError(OutlookError):
    """指定された Outlook フォルダが存在しない。"""

    def __init__(self, folder: str, existing_folders: list[str]) -> None:
        names = "、".join(existing_folders) if existing_folders else "（なし）"
        super().__init__(f"Outlook フォルダ「{folder}」が見つかりません。存在するフォルダ: {names}")


class OutlookAttachmentNotFoundError(OutlookError):
    """下書きへ添付するファイルが存在しない。"""

    def __init__(self, path: Path) -> None:
        super().__init__(
            f"添付ファイルが見つかりません: {path}。"
            "パスを確認してください。下書きは作成していません。"
        )
