"""comken/core/dates/_format.py — yyyymmdd ⇔ 日付 の変換。

8 桁の数字列（``20261005``）と ``datetime.date`` の相互変換。和暦・日本語表記・
Excel シリアル値など別書式は扱わない（必要になったら別関数を足す）。

``parse_yyyymmdd()`` は **明示的に変換を頼んだとき**に使うので、読めなかったら
黙って ``None`` を返さず例外で止める（``parse_cell_date()`` の方針と逆になる
のは、import 側で「読めない値を弾きたい」のか「無い行を数えたい」のかで
意図が違うため）。
"""

import datetime as _dt

from comken.exceptions import DateFormatError

# yyyymmdd 形式の 8 桁文字列。ゼロ埋め必須・区切り文字なし
_YYYYMMDD_FORMAT: str = "%Y%m%d"
_YYYYMMDD_LENGTH: int = 8


def format_yyyymmdd(target: _dt.date | _dt.datetime) -> str:
    """``target`` を ``yyyymmdd`` 形式の 8 桁文字列に変換する。

    1 桁の月日でもゼロ埋めする（``2026-10-05`` → ``"20261005"``）。
    ``datetime.datetime`` を渡されたときは ``date()`` で日付部分だけ変換する
    （時刻は捨て、日付だけを 8 桁にする）。

    Args:
        target: 変換対象の日付（``datetime.date`` または ``datetime.datetime``）。

    Returns:
        ``"20261005"`` のような 8 桁数字文字列。
    """
    day = target.date() if isinstance(target, _dt.datetime) else target
    return day.strftime(_YYYYMMDD_FORMAT)


def parse_yyyymmdd(text: str) -> _dt.date:
    """``yyyymmdd`` 形式の 8 桁文字列を ``datetime.date`` に変換する。

    前後の空白は ``str.strip()`` で取り除いてから判定する。
    **数字ちょうど 8 桁** 以外（区切り文字付き、全角、桁過不足）は
    ``DateFormatError``。存在しない日付（``"20260230"``）も ``DateFormatError``
    （``datetime`` 側のチェックで弾かれる）。

    Args:
        text: ``"20261005"`` のような 8 桁数字文字列（前後の空白は許容）。

    Returns:
        変換した ``datetime.date``。

    Raises:
        DateFormatError: 8 桁でない・数字以外を含む・存在しない日付のとき。
    """
    stripped = text.strip()
    if len(stripped) != _YYYYMMDD_LENGTH or not stripped.isascii() or not stripped.isdigit():
        raise DateFormatError(f"yyyymmdd 形式ではありません（8 桁の数字列が必要です）: {text!r}")
    try:
        return _dt.datetime.strptime(stripped, _YYYYMMDD_FORMAT).date()  # noqa: DTZ007  # 業務日付として naive で扱う
    except ValueError as error:
        raise DateFormatError(f"yyyymmdd 形式の日付として解釈できません: {text!r}") from error
