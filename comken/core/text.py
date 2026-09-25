"""comken/core/text.py — テキスト正規化ユーティリティ

業務データでよくある文字列の揺れを正規化する。
仕様:
    normalize() は unicodedata.normalize("NFKC") を使うため:
        - 全角英数字・記号 → 半角
        - 半角カタカナ     → 全角カタカナ
        - 合字（㌔, ㍉ など）→ 展開（km, mm など）
    がすべて同時に適用される。
"""

import codecs
import unicodedata

# Windows の Shift_JIS は cp932（Microsoft 拡張）で扱う。Python の ``codecs`` で
# ``Shift_JIS`` を指定しても同じとは限らないため、業務ファイルが前提の comken では
# cp932 に寄せる。
_CP932_ALIASES = frozenset(
    {"sjis", "shift-jis", "shiftjis", "windows-31j", "ms932", "mskanji", "ms-kanji"}
)


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


def normalize_encoding(name: str) -> str:
    """文字コードの表記を Python の codec 名にそろえる。

    仕様:
        - 前後の空白を除き、小文字化し ``_`` を ``-`` に置き換える
          （``UTF-8`` → ``utf-8``、``Shift_JIS`` → ``shift-jis``）
        - 別名を次の対応で ``cp932`` / ``utf-8`` / ``utf-8-sig`` にそろえる:
            ``utf8`` → ``utf-8``、``utf8-sig`` / ``utf-8-bom`` → ``utf-8-sig``、
            ``sjis`` / ``shift-jis`` / ``shiftjis`` / ``windows-31j`` /
            ``ms932`` / ``mskanji`` / ``ms-kanji`` → ``cp932``
        - 上の対応に無い名前は ``codecs.lookup(name)`` で有効か確かめ、
          有効なら **正規化後の名前（小文字・``-`` 区切り）のまま** 返す
        - 無効なら ``ValueError``

    ``"auto"`` は特別扱いしない。``None`` が自動判定で、``"auto"`` は無効な名前。

    Args:
        name: 表記ゆれを含む文字コード名。

    Returns:
        Python の codec 名として使える正規化された名前。

    Raises:
        ValueError: ``name`` が既知の別名にも有効な codec 名にも一致しないとき。
            メッセージには、渡された名前、省略すると自動判定であること、
            主に使う名前（``cp932`` / ``utf-8-sig`` / ``utf-8``）を含める。
    """
    normalized = name.strip().lower().replace("_", "-")
    if normalized == "utf8":
        return "utf-8"
    if normalized in ("utf8-sig", "utf-8-bom"):
        return "utf-8-sig"
    if normalized in _CP932_ALIASES:
        return "cp932"
    try:
        codecs.lookup(normalized)
    except LookupError as error:
        raise ValueError(
            f"未知の文字コード名です: {name!r}。"
            "\n対処: encoding 引数を省略すると自動判定します。"
            "明示するときは主に cp932 / utf-8-sig / utf-8 を指定してください。"
        ) from error
    return normalized


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
