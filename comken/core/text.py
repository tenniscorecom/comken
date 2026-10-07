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


def remove_spaces(text: str) -> str:
    """文字列中の半角・全角スペースをすべて除去する。

    電話番号・郵便番号など、スペースを含んではいけない値の正規化に使う。

    Args:
        text: 処理する文字列。

    Returns:
        スペースを除去した文字列。
    """
    return text.replace("　", "").replace(" ", "").replace("\t", "")


def is_true_word(text: str) -> bool:
    """英語の "true" 表記かどうかを判定する（大文字小文字は問わない）。

    config.ini の bool 変換と、Excel 管理表（レポート管理表・スケジュール管理表など）の
    「有効」列判定の両方が使う、共通の "true" 判定。前後の空白は無視する
    （config.ini 側は事前に ``strip()`` 済みの値を渡す想定だが、
    Excel のセル値は前後に空白が付いたまま渡ってくることがあるため、ここでも取る）。

    Args:
        text: 判定する文字列。

    Returns:
        "true"（大文字小文字問わず）と一致すれば True。
    """
    return text.strip().lower() == "true"
