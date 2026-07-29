"""CSV の文字コード定数。"""


class Encoding:
    """CsvReader / CsvWriter の encoding 引数に使う定数。"""

    AUTO = "auto"  # UTF-8 → CP932 の順に自動判定（CsvReader のみ）
    UTF8_SIG = "utf-8-sig"  # BOM 付き UTF-8（Excel でそのまま開ける）
    CP932 = "cp932"  # Shift-JIS（Windows の従来形式）
