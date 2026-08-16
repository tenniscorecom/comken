"""comken/core/utils/files/naming/date.py — 日付を付けたファイル名の組み立て。"""

from ...clock import now


class DateNameBuilder:
    """今日の日付を付けたファイル名を組み立てる。

    日付はファイル名の属性ではなく「付け方」なので、コンストラクタではなく
    prefix() / suffix() の呼び出し時に決める。

    """

    def __init__(self, name: str, ext: str = ".xlsx") -> None:
        """
        Args:
            name: ファイル名（拡張子なし）。
            ext: 拡張子（デフォルト: ".xlsx"）。ドットなしで渡しても補完される。
        """
        self._name = name
        self._ext = ext if ext.startswith(".") else f".{ext}"

    def plain(self) -> str:
        """日付なしのファイル名を返す。"""
        return f"{self._name}{self._ext}"

    def prefix(self, date_format: str = "%Y%m%d") -> str:
        """今日の日付を前に付けたファイル名を返す（例: 20260711_売上レポート.xlsx）。"""
        return f"{self._current_time(date_format)}_{self._name}{self._ext}"

    def suffix(self, date_format: str = "%Y%m%d") -> str:
        """今日の日付を後ろに付けたファイル名を返す（例: 売上レポート_20260711.xlsx）。"""
        return f"{self._name}_{self._current_time(date_format)}{self._ext}"

    @staticmethod
    def _current_time(date_format: str) -> str:
        return now().strftime(date_format)
