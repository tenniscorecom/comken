"""Excel COM の保存形式定数。"""


class FileFormat:
    """Workbook.SaveAs に渡す FileFormat 定数（Excel の XlFileFormat）。

    save_as() では元ファイルと同じ形式が自動で使われるため、通常は指定不要。
    形式を変換して保存する場合だけ file_format 引数で渡す。
    """

    XLSX = 51  # xlOpenXMLWorkbook
    XLSM = 52  # xlOpenXMLWorkbookMacroEnabled
    XLSB = 50  # xlExcel12
    XLS = 56  # xlExcel8
    CSV = 6  # xlCSV
