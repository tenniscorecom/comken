"""comken/core/calendar/company.py — 会社独自の休業日ルール。

国民の祝日（内閣府 CSV + 計算値）に対する会社都合の休業日（年末年始休暇など）
を **コード直書きのルール** で判定する。国民の祝日とは別概念なので、
「国民の祝日に重なった場合は国民の祝日が先勝ち」「土日と重なっても振替は行わない」
という扱いをここで固定する（国民の祝日側で吸収する）。

実行時の **今日** や年の範囲には依存しない。``company_holiday_name(date)`` は
``date`` の月日が ``COMPANY_HOLIDAYS`` のどれかに当たればその名前を返し、
``COMPANY_HOLIDAYS_EXTRA`` に登録された年月日の日付なら ``EXTRA_HOLIDAY_NAME``
を返す。どれにも当たらないなら ``None``。

``COMPANY_HOLIDAYS`` / ``COMPANY_HOLIDAYS_EXTRA`` を編集するだけで休みの
ルールが変わる（年範囲の管理は要らない — ルールで毎回判定するため）。
"""

import datetime as _dt
from typing import Final

# 毎年繰り返す会社の休業日。**年は書かない**（毎年その月日が休みになる）。
# 休みを増やすときは (月, 日) を書き足すだけでよい。年またぎの年末年始も
# 月日で書けばそのまま毎年適用される。
COMPANY_HOLIDAYS: Final[dict[str, tuple[tuple[int, int], ...]]] = {
    "年末年始休暇": ((12, 29), (12, 30), (12, 31), (1, 1), (1, 2), (1, 3)),
}

# その年だけの臨時の休み。年月日で書く。
# 例: 2026年だけ 12/28 も休みにする → date(2026, 12, 28) を足す。
# 古くなった年の行は消してよい（消しても過去の判定が変わるだけで、運用に影響しない）。
COMPANY_HOLIDAYS_EXTRA: Final[tuple[_dt.date, ...]] = ()

EXTRA_HOLIDAY_NAME: Final[str] = "会社休業日"


def company_holiday_name(target: _dt.date) -> str | None:
    """``target`` が会社休日に当たればその名称、なければ ``None``。

    判定は **ルールで実行時に**行う（年範囲を持たない）。

    - ``target`` の ``(月, 日)`` が ``COMPANY_HOLIDAYS`` のいずれかの値に
      当たれば、その**キー**（例: "年末年始休暇"）を返す。
    - ``target`` が ``COMPANY_HOLIDAYS_EXTRA`` に登録された年月日なら
      ``EXTRA_HOLIDAY_NAME``（既定 "会社休業日"）を返す。
    - 国民の祝日との重複はここでは解決しない（呼び出し側で国民の祝日を
      先勝ち判定する）。
    """
    month_day = (target.month, target.day)
    for name, month_days in COMPANY_HOLIDAYS.items():
        if month_day in month_days:
            return name
    if target in COMPANY_HOLIDAYS_EXTRA:
        return EXTRA_HOLIDAY_NAME
    return None


__all__ = [
    "COMPANY_HOLIDAYS",
    "COMPANY_HOLIDAYS_EXTRA",
    "EXTRA_HOLIDAY_NAME",
    "company_holiday_name",
]
