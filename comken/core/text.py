"""comken/core/text.py — テキスト正規化ユーティリティ

業務データでよくある文字列の揺れを正規化する。
仕様:
    normalize() は unicodedata.normalize("NFKC") を使うため:
        - 全角英数字・記号 → 半角
        - 半角カタカナ     → 全角カタカナ
        - 合字（㌔, ㍉ など）→ 展開（km, mm など）
    がすべて同時に適用される。
"""

import unicodedata


def normalize(value: object) -> str:
    """表データの値を比較しやすい文字列へ正規化する。

    主な変換:
        - 全角英数字・記号 → 半角（ａ→a, １→1, （→(, ．→.）
        - 半角カタカナ     → 全角カタカナ（ｱ→ア, ｶﾞ→ガ）
        - 合字             → 展開（㌔→km, ㍉→mm）

    Args:
        value: Excel / CSV から得た値。``None`` は空文字として扱う。

    Returns:
        正規化後の文字列。
    """
    if value is None:
        return ""
    return unicodedata.normalize("NFKC", str(value)).strip()


def strip_spaces(text: str) -> str:
    """前後の半角・全角スペースを除去する。

    str.strip() は全角スペース（U+3000）を除去しないため、
    業務データの氏名・住所フィールドで使うのに向いている。

    Args:
        text: 処理する文字列。

    Returns:
        前後のスペースを除去した文字列。
    """
    return text.strip("　 \t\n\r")


def remove_spaces(text: str) -> str:
    """文字列中の半角・全角スペースをすべて除去する。

    電話番号・郵便番号など、スペースを含んではいけない値の正規化に使う。

    Args:
        text: 処理する文字列。

    Returns:
        スペースを除去した文字列。
    """
    return text.replace("　", "").replace(" ", "").replace("\t", "")
