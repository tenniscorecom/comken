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

__all__ = ["is_enabled_mark", "is_true_word", "normalize", "remove_spaces"]


def normalize(value: object) -> str:
    """値を、比較（突合）のための文字列にそろえる。

    ``Table.diff()`` のキー・値の比較と ``Table.transfer_from()`` のキーの突合は、
    この関数でそろえてから比べる。元に戻せない変換（NFKC）なので、
    **書き戻すデータには使わず、比べるときの鍵にだけ使う**。

    主な変換:
        - 全角英数字・記号 → 半角（ａ→a, １→1, （→(, ．→.）
        - 半角カタカナ     → 全角カタカナ（ｱ→ア, ｶﾞ→ガ）
        - 合字・丸数字     → 展開（㌔→キロ, ㈱→(株), ①→1）
        - 整数値の小数     → 整数（1000.0 → "1000"。Excel の数値と CSV の文字列を一致させる）
        - 前後の空白を除く（全角空白も）

    Excel の ``ASC`` / ``JIS`` とは別の変換（NFKC は英数字を半角・カナを全角にする）。

    Args:
        value: Excel / CSV から得た値。``None`` は空文字として扱う。

    Returns:
        正規化後の文字列。
    """
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
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

    Note:
        仕様上、 ``"1"`` / ``"yes"`` / ``"on"`` などはここで False になる
        （config.ini の整数 ``1`` が bool 扱いになる事故を防ぐため）。 Excel
        管理表のような日本語・記号混じりのセルで ``"1"`` を有効扱いにしたい
        ときは ``is_enabled_mark`` を使う。
    """
    return text.strip().lower() == "true"


# Excel 管理表の「有効」列で真とみなす語（``"true"`` を除く）。
# ``is_true_word`` が ``"true"`` を True にするので、ここでは二重管理しない。
# 大文字小文字は区別せず、前後の空白（半角・全角）は ``is_enabled_mark`` 側で
# 落とす。 業務上「○/×」運用を続けるために必要なので、ここで固定の語集合として
# 持つ（呼び出し側に持たせると呼び出し箇所ごとにズレる）。
_ENABLED_MARKS: tuple[str, ...] = ("有効", "○", "o", "yes", "1", "on", "はい")


def is_enabled_mark(value: object) -> bool:
    """Excel / CSV の管理表セルが「有効」を表すかどうかを判定する。

    真とみなす値:

    - ``bool``: そのまま返す（``True`` / ``False``）
    - ``int``: ``1`` だけ True、 それ以外は False
    - ``str``: 前後の空白（半角・全角）を除いたあと、大文字小文字を無視して
      ``is_true_word`` を通すか、以下の語のいずれかに一致すれば True::

          "有効" / "○" / "o" / "yes" / "1" / "on" / "はい" / "true"

    それ以外（``None`` / 空文字 / ``"×"`` / ``"無効"`` / ``"no"`` / ``"0"`` /
    ``"off"`` / ``"いいえ"`` などの数値・文字列）は False。

    Args:
        value: セルから得た値。 Excel のセルは ``bool`` / ``int`` / ``str`` /
            ``None`` のどれでも来うる。

    Returns:
        「有効」とみなせる値なら True。

    Note:
        ``is_true_word`` とは語集合が違う。 ``"1"`` を True にするのは
        Excel 管理表の視認性のためで、 ``config.ini`` の ``1`` を bool に
        しない設計（``is_true_word("1") is False``）を壊さないために、
        別の関数として公開している。
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value == 1
    text = str(value).strip().lower()
    if not text:
        return False
    if is_true_word(text):
        return True
    return text in _ENABLED_MARKS
