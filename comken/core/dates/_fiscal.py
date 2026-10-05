"""comken/core/dates/_fiscal.py — 年度（4月始まり）。

日本の会社慣習に合わせて **4月始まり** の年度だけを扱う。
年度の初日・末日・上期下期・四半期は今は作っていない（要るときに足す）。
4月始まりは会社で変わる値ではないため設定ファイル化せず、コードに固定する。
"""

import datetime as _dt

# 年度の開始月（4 月始まりは日本の会計年度・多くの社内運用に合わせた既定値）
FISCAL_YEAR_START_MONTH: int = 4


def fiscal_year(target: _dt.date | _dt.datetime) -> int:
    """``target`` が属する年度（4月始まり）を返す。

    4〜12月は ``target.year`` と同じ、1〜3月は ``target.year - 1``。
    ``datetime.datetime`` を渡されたときは ``date()`` で日付部分だけ判定する。

    Args:
        target: 対象日付（``datetime.date`` または ``datetime.datetime``）。

    Returns:
        ``target`` が属する年度の西暦。
    """
    day = target.date() if isinstance(target, _dt.datetime) else target
    return day.year if day.month >= FISCAL_YEAR_START_MONTH else day.year - 1
