"""Excel で使う色定数。

ExcelFile.set_fill() の color 引数や openpyxl の色指定にそのまま渡せる RGB 16進値。
ここにない色は 16進値を直接渡す（例: "CCE5FF"）。

使い方:
    from comken.excel import Color

    with ExcelFile("data.xlsx") as f:
        f.set_fill("Sheet1", row=2, col=1, color=Color.YELLOW)
        f.set_fill("Sheet1", row=3, col=1, color="CCE5FF")  # 好きな色は16進で
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
