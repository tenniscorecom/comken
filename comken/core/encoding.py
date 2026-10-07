"""comken/core/encoding.py — 文字コードの名前・別名・コードページ番号の唯一の置き場。

業務データで扱う文字コードの **名前・別名・Windows コードページ番号** をここに集約する。
別名の吸収は Python の ``codecs.lookup`` に任せ、comken 固有の規則は次の2つだけ持つ:

- ``shift_jis`` 系 (``sjis`` / ``shift-jis`` / ``shiftjis``) は Microsoft 拡張の ``cp932`` に寄せる
  （Windows の業務ファイルは cp932 が前提のため、``codecs`` の ``shift_jis`` とは区別する）
- ``utf8-sig`` / ``utf-8-bom`` は ``utf-8-sig`` として扱う（Python の codec は ``utf8-sig`` を
  受け付けず、利用者の表記揺れをここで吸収するため）

新しい文字コード・コードページを足すときは、このファイルだけを触る。
"""

from __future__ import annotations

import codecs

# Python の codec 名そのもの。``codecs.lookup`` を通しても同じ正規名へ戻ることを
# ``tests/test_encoding.py`` で担保する。
CP932 = "cp932"
UTF8 = "utf-8"
UTF8_SIG = "utf-8-sig"

# Access の ``TransferText`` に渡す Windows コードページ番号。
# Access は BOM なし UTF-8 を直接扱えない（``utf-8-sig`` だけ受け付ける）ことに対応して、
# ``utf-8`` を含めていない。``utf-8`` を渡したいケースは今のところ無い。
_ENCODING_CODE_PAGES: dict[str, int] = {
    CP932: 932,
    UTF8_SIG: 65001,
}


def normalize_encoding(name: str) -> str:
    """文字コードの表記を Python の codec 名にそろえる。

    仕様:

    - 前後の空白を除き、小文字化し ``_`` を ``-`` に置き換える
      （``UTF-8`` → ``utf-8``、``Shift_JIS`` → ``shift-jis``）
    - ``utf8-sig`` / ``utf-8-bom`` は ``codecs.lookup`` が受け付けないため
      先に ``utf-8-sig`` へそろえる
    - 上の前段を抜けた名前は ``codecs.lookup`` で正規名を引いたうえで:
        - ``utf-8`` / ``utf-8-sig`` / ``cp932`` は正規名をそのまま返す
        - ``shift_jis`` は業務ファイル前提で ``cp932`` に寄せる
          （``sjis`` / ``shift-jis`` / ``shiftjis`` も ``codecs.lookup`` で
          ``shift_jis`` に正規化されるため同じ扱いで ``cp932`` になる）
        - それ以外の有効な名前は **正規化後の名前（小文字・``-`` 区切り）のまま** 返す
    - 無効なら ``ValueError``

    ``"auto"`` は特別扱いしない。``None`` が自動判定で、``"auto"`` は無効な名前。

    Args:
        name: 表記ゆれを含む文字コード名。

    Returns:
        Python の codec 名として使える正規化された名前。

    Raises:
        ValueError: ``name`` が無効な codec 名（``"auto"`` を含む）のとき。
            メッセージには、渡された名前、省略すると自動判定であること、
            主に使う名前（``cp932`` / ``utf-8-sig`` / ``utf-8``）を含める。
    """
    normalized = name.strip().lower().replace("_", "-")
    # ``codecs.lookup`` が受け付けない表記を先に正規化する。
    # ``utf8-sig`` は ``_`` → ``-`` で ``utf-8-sig`` になるので結果的に吸収されるが、
    # ``utf-8-bom`` は codec に存在しないためここで扱う。
    if normalized in ("utf8-sig", "utf-8-bom"):
        return UTF8_SIG
    try:
        codec = codecs.lookup(normalized).name
    except LookupError as error:
        raise ValueError(
            f"未知の文字コード名です: {name!r}。"
            "\n対処: encoding 引数を省略すると自動判定します。"
            "明示するときは主に cp932 / utf-8-sig / utf-8 を指定してください。"
        ) from error
    if codec in (UTF8, UTF8_SIG, CP932):
        return codec
    if codec == "shift_jis":
        # 業務ファイルは Microsoft 拡張の cp932 に寄せる。
        return CP932
    return normalized


def code_page(name: str) -> int:
    """文字コード名から Access 等の COM API に渡す Windows コードページ番号を返す。

    ``name`` を ``normalize_encoding`` で吸収してから ``_ENCODING_CODE_PAGES`` を引く。
    Access の ``TransferText`` は BOM なし UTF-8 を扱えないため、``utf-8`` を渡すと
    ``ValueError`` になる（Access の制約なので、今の挙動をそのまま残す）。

    Args:
        name: 文字コード名。表記ゆれは ``normalize_encoding`` で吸収する。

    Returns:
        Windows のコードページ番号（``cp932`` → 932、``utf-8-sig`` → 65001）。

    Raises:
        ValueError: ``name`` が無効な codec 名、または ``_ENCODING_CODE_PAGES``
            に登録されていない codec（``utf-8`` / ``euc-jp`` など）のとき。
            メッセージには、登録されている codec 一覧を含める。
    """
    normalized = normalize_encoding(name)
    if normalized not in _ENCODING_CODE_PAGES:
        choices = sorted(_ENCODING_CODE_PAGES)
        raise ValueError(
            f"encoding は次から指定してください: {choices}"
            "\n対処: encoding は cp932（既定）か utf-8-sig を指定してください。"
        )
    return _ENCODING_CODE_PAGES[normalized]


# Web 側（Salesforce など）に渡す「charset 名」の対応表。
# ``Shift_JIS`` は Salesforce の書き出しの既定として使ってきた名前。``UTF-8`` は
# 標準的な名前だが、本物の Salesforce 組織で受け付けることは未確認（2026-10-07 時点）。
# Salesforce が受け付ける名前を comken が全部は知らないため、表にない有効な
# 名前は ``charset_name`` 側でそのまま返す（``normalize_encoding`` の
# ``ValueError`` はそのまま通す）。
_CHARSET_NAMES: dict[str, str] = {
    CP932: "Shift_JIS",
    UTF8: "UTF-8",
    UTF8_SIG: "UTF-8",
}


def charset_name(name: str) -> str:
    """Web 側（Salesforce など HTTP のパラメータ）に渡す文字コード名を返す。

    内部では ``normalize_encoding`` で ``name`` を吸収してから ``_CHARSET_NAMES``
    を引く。表にヒットすれば Salesforce など Web 側が受け付ける標準的な名前
    （``Shift_JIS`` / ``UTF-8``）にそろえて返し、表にない **有効な** 名前は
    ユーザーが渡した文字列をそのまま返す
    （``normalize_encoding`` が無効と判定した名前は ``ValueError``）。

    表に載っているのは ``cp932`` / ``utf-8`` 系だけ（``UTF-8`` は本物の組織では未確認）。
    逆に表に無い名前でも Web 側が受け付ける場合はあるので、``ISO-8859-1`` や
    ``euc-jp`` のような名前は渡した文字列のまま返す。これにより、ユーザーが
    ``cp932`` と書けば Salesforce には ``Shift_JIS`` が送られ、その他の名前は
    そのまま渡る。

    Args:
        name: 文字コード名。表記ゆれは ``normalize_encoding`` で吸収する。

    Returns:
        Web 側に渡す文字コード名。表にヒットすれば ``Shift_JIS`` / ``UTF-8``
        のいずれかにそろい、ヒットしなければ ``name`` をそのまま返す。

    Raises:
        ValueError: ``name`` が ``normalize_encoding`` で無効と判定されたとき。
    """
    normalized = normalize_encoding(name)
    return _CHARSET_NAMES.get(normalized, name)
