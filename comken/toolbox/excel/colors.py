"""comken/toolbox/excel/colors.py — Excel でよく使う色の定数（RGB 16進値）。

``Sheet.set_background(cell, color)`` の ``color`` に渡すと、
セル背景色を ``PatternFill("solid", fgColor=color)`` で塗れる。
"""


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


__all__ = ["Color"]
