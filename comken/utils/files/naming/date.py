"""日付を付けたファイル名の組み立て。"""

from ...clock import today


class DateNameBuilder:
    """今日の日付を付けたファイル名を組み立てる。

    日付はファイル名の属性ではなく「付け方」なので、コンストラクタではなく
    prefix() / suffix() の呼び出し時に決める。

    使い方:
        DateNameBuilder("売上レポート").plain()                 # → "売上レポート.xlsx"
        DateNameBuilder("売上レポート").prefix()                # → "20260711_売上レポート.xlsx"
        DateNameBuilder("売上レポート").suffix()                # → "売上レポート_20260711.xlsx"
        DateNameBuilder("ログ", ext=".csv").prefix()            # → "20260711_ログ.csv"
        DateNameBuilder("月次").prefix(date_format="%Y%m")      # → "202607_月次.xlsx"
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
        return f"{self._today(date_format)}_{self._name}{self._ext}"

    def suffix(self, date_format: str = "%Y%m%d") -> str:
        """今日の日付を後ろに付けたファイル名を返す（例: 売上レポート_20260711.xlsx）。"""
        return f"{self._name}_{self._today(date_format)}{self._ext}"

    @staticmethod
    def _today(date_format: str) -> str:
        return today().strftime(date_format)
