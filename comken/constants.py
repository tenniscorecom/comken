"""comken/constants.py — CSV・Excel・ファイル操作で使う、小さな公開定数クラス。"""


class Encoding:
    """CsvReader / CsvWriter の encoding 引数に使う定数。"""

    AUTO = "auto"
    UTF8_SIG = "utf-8-sig"
    CP932 = "cp932"


class Color:
    """Excel でよく使う色の定数（RGB 16進値）。"""

    RED = "FF0000"
    PINK = "FFCCCC"
    ORANGE = "FFC000"
    YELLOW = "FFFF00"
    LIGHT_YELLOW = "FFF2CC"
    GREEN = "00B050"
    LIGHT_GREEN = "CCFFCC"
    BLUE = "0070C0"
    LIGHT_BLUE = "DDEBF7"
    PURPLE = "7030A0"
    GRAY = "808080"
    LIGHT_GRAY = "D9D9D9"
    WHITE = "FFFFFF"
    BLACK = "000000"


class FileFormat:
    """Workbook.SaveAs に渡す Excel の保存形式定数。"""

    XLSX = 51
    XLSM = 52
    XLSB = 50
    XLS = 56
    CSV = 6


class SortBy:
    """FileFinder.latest() の by 引数に使う定数。"""

    NAME = "name"
    UPDATED = "updated"


__all__ = ["Encoding", "Color", "FileFormat", "SortBy"]
