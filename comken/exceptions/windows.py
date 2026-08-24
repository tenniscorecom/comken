"""comken/exceptions/windows.py — Windows 操作に関する例外。"""

from comken.exceptions.base import ComkenError


class WindowNotFoundError(ComkenError):
    """指定したウィンドウが見つからない

    発生箇所: ``WindowHandler.__init__``

    対処:
        対象ウィンドウが開いているか、タイトル（完全一致）が想定どおりかを確認する
    """

    def __init__(self, title: str) -> None:
        super().__init__(
            f"ウィンドウが見つかりません: {title}\n"
            "対象のウィンドウが開いているか、タイトル（完全一致）が想定どおりかを確認してください。"
        )
