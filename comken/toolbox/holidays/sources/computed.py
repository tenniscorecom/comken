"""comken/toolbox/holidays/sources/computed.py — 計算で祝日を組み立てるソース。

内閣府の ``syukujitsu.csv`` に頼らず、祝日法で定義された規則だけで
``Holiday`` を組み立てる。`mokejp/holidays_jp` (MIT) のアルゴリズムを
comken 流で書き直した実装（純粋計算）。

このモジュールは **外を一切触らない** — `requests` も標準ライブラリ以外も
import しないため、オフラインの社内 BO 環境でもそのまま動く。
``CabinetOfficeCsvSource`` と並列に置き、
``HolidayCalendar.from_sources([Cabinet, Computed])`` のように
和集合で運用する想定。

カバーする規則:

- 固定日（元日・建国記念の日・昭和の日 など）
- ハッピーマンデー（成人の日・海の日・敬老の日・体育／スポーツの日）
- 天皇誕生日（年で日付が変わる：昭和 → 平成 → 令和）
- 春分・秋分（近似式。1980-2099 が高精度範囲、2100- は別係数で低精度対応）
- 国民の休日（1985-。シルバーウィークと 5/4 のサンドイッチ）
- 振替休日（2007年改正以降。日曜の祝日を後ろに倒す）
- 2020 年オリンピック特例（海の日・スポーツの日・山の日）
- 2019 年 即位関連特例（天皇の即位の日・即位礼正殿の儀の行われる日）
- 会社休日（ファイル先頭の ``COMPANY_HOLIDAYS`` リストに追加する）
"""

import datetime as _dt
import logging
from itertools import pairwise
from typing import Final

from comken.toolbox.holidays.calendar import Holiday, HolidaySource

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# 会社休日 (必要に応じてここに追加)
# ─────────────────────────────────────────────────────────────────────
# 形式 (3 種類):
#   1. 単発 (int 月, int 日, str 名称) - 毎年同じ月日
#   2. 期間 (int 開始月, int 開始日, int 終了月, int 終了日, str 名称) - 毎年繰り返す
#   3. 特定年のみ (_dt.date, _dt.date, str 名称) - start〜end の 1回だけ
#
# 例 (コメントアウトで残す):
#   (12, 29, 1, 3, "年末年始休暇"),  # 毎年 12/29 - 1/3 (年跨ぎ)
#   (8, 13, 8, 16, "夏季休暇"),     # 毎年 8/13 - 8/16
#   (4, 1, "創立記念日"),           # 毎年 4/1
#   (_dt.date(2025, 11, 4), _dt.date(2025, 11, 5), "臨時休業"),  # 2025 だけ
#
# 追加したら tests/test_holidays.py::TestCompanyHolidays にテストも 1件足すこと。
COMPANY_HOLIDAYS: Final[list[tuple]] = [
    # ここに追加する
]


# 既定の対象範囲。1948-07-20 が祝日法施行日。春分／秋分の近似式は 2099 年までが高精度。
DEFAULT_FROM_YEAR: Final[int] = 1948
DEFAULT_TO_YEAR: Final[int] = 2099


# ── ヘルパー ──────────────────────────────────────────────────────────────


def _vernal_equinox_day(year: int) -> int:
    """春分日を近似計算する（``mokejp/holidays_jp`` と同アルゴリズム）。

    1980-2099 が高精度、2100- は別係数で低精度対応。
    """
    y = year - 1980
    if year >= 2100:
        return int(21.8510 + 0.242194 * y - y // 4)
    if year >= 1980:
        return int(20.8431 + 0.242194 * y - y // 4)
    return int(20.8357 + 0.242194 * y - y // 4)


def _autumnal_equinox_day(year: int) -> int:
    """秋分日を近似計算する（``mokejp/holidays_jp`` と同アルゴリズム）。"""
    y = year - 1980
    if year >= 2100:
        return int(24.2488 + 0.242194 * y - y // 4)
    if year >= 1980:
        return int(23.2488 + 0.242194 * y - y // 4)
    return int(23.2588 + 0.242194 * y - y // 4)


def _nth_weekday(year: int, month: int, nth: int, weekday: int) -> _dt.date:
    """``year`` 年 ``month`` 月の ``nth`` 番目の ``weekday`` (0=月曜) を返す。

    例: ``_nth_weekday(2026, 1, 2, 0)`` → 2026-01-12（成人の日 = 1月 第2月曜）。
    """
    first_day = _dt.date(year, month, 1)
    # 月初日の曜日 (0=月, …, 6=日)
    first_weekday = first_day.weekday()
    # 第 1 ``weekday`` までのずれ
    offset_to_first = (weekday - first_weekday) % 7
    first_target_day = 1 + offset_to_first
    # 第 nth ``weekday`` の日にち
    day = first_target_day + (nth - 1) * 7
    return _dt.date(year, month, day)


# ── メインの組み立て ──────────────────────────────────────────────────────


def _fixed_holidays(year: int) -> list[Holiday]:
    """固定日の祝日を ``year`` 年について返す。"""
    holidays: list[Holiday] = []
    if year >= 1949:
        holidays.append(Holiday(_dt.date(year, 1, 1), "元日"))
    if year >= 1966:
        holidays.append(Holiday(_dt.date(year, 2, 11), "建国記念の日"))
    # 4/29 は年で名称が変わる
    if year >= 2007:
        holidays.append(Holiday(_dt.date(year, 4, 29), "昭和の日"))
    elif year >= 1989:
        holidays.append(Holiday(_dt.date(year, 4, 29), "みどりの日"))
    elif year >= 1948:
        holidays.append(Holiday(_dt.date(year, 4, 29), "天皇誕生日"))
    holidays.append(Holiday(_dt.date(year, 5, 3), "憲法記念日"))
    if year >= 2007:
        holidays.append(Holiday(_dt.date(year, 5, 4), "みどりの日"))
    holidays.append(Holiday(_dt.date(year, 5, 5), "こどもの日"))
    holidays.append(Holiday(_dt.date(year, 11, 3), "文化の日"))
    holidays.append(Holiday(_dt.date(year, 11, 23), "勤労感謝の日"))
    return holidays


def _adults_day(year: int) -> Holiday | None:
    """成人の日を返す（1949-1999 = 1/15、2000- = 1月 第2月曜）。"""
    if 1949 <= year <= 1999:
        return Holiday(_dt.date(year, 1, 15), "成人の日")
    if year >= 2000:
        return Holiday(_nth_weekday(year, 1, 2, 0), "成人の日")
    return None


def _marine_day(year: int) -> Holiday | None:
    """海の日を返す。2020 は 7/23、それ以外は 1996-2002 = 7/20、2003- = 7月 第3月曜。"""
    if year == 2020:
        return Holiday(_dt.date(2020, 7, 23), "海の日")
    if 1996 <= year <= 2002:
        return Holiday(_dt.date(year, 7, 20), "海の日")
    if year >= 2003:
        return Holiday(_nth_weekday(year, 7, 3, 0), "海の日")
    return None


def _respect_for_the_aged_day(year: int) -> Holiday | None:
    """敬老の日を返す。1966-2002 = 9/15、2003- = 9月 第3月曜。"""
    if 1966 <= year <= 2002:
        return Holiday(_dt.date(year, 9, 15), "敬老の日")
    if year >= 2003:
        return Holiday(_nth_weekday(year, 9, 3, 0), "敬老の日")
    return None


def _sports_day(year: int) -> Holiday | None:
    """体育の日 / スポーツの日を返す。

    1966-1999 = 10/10、2000-2019 = 10月 第2月曜（体育の日）、
    2020 = 7/24（スポーツの日）、2021- = 10月 第2月曜（スポーツの日）。
    """
    if year == 2020:
        return Holiday(_dt.date(2020, 7, 24), "スポーツの日")
    if 1966 <= year <= 1999:
        return Holiday(_dt.date(year, 10, 10), "体育の日")
    if 2000 <= year <= 2019:
        return Holiday(_nth_weekday(year, 10, 2, 0), "体育の日")
    if year >= 2021:
        return Holiday(_nth_weekday(year, 10, 2, 0), "スポーツの日")
    return None


def _mountain_day(year: int) -> Holiday | None:
    """山の日を返す。2020 のみ 8/10、それ以降 2016- は 8/11。"""
    if year == 2020:
        return Holiday(_dt.date(2020, 8, 10), "山の日")
    if year >= 2016:
        return Holiday(_dt.date(year, 8, 11), "山の日")
    return None


def _emperors_birthday(year: int) -> Holiday | None:
    """天皇誕生日を返す。1989-2018 = 12/23、2020- = 2/23。2019 は変則のため None。"""
    if 1989 <= year <= 2018:
        return Holiday(_dt.date(year, 12, 23), "天皇誕生日")
    if year >= 2020:
        return Holiday(_dt.date(year, 2, 23), "天皇誕生日")
    return None


def _equinox_holidays(year: int) -> list[Holiday]:
    """春分・秋分の日を返す。"""
    holidays: list[Holiday] = []
    if year >= 1949:
        holidays.append(Holiday(_dt.date(year, 3, _vernal_equinox_day(year)), "春分の日"))
    if year >= 1948:
        holidays.append(Holiday(_dt.date(year, 9, _autumnal_equinox_day(year)), "秋分の日"))
    return holidays


def _one_off_year_holidays(year: int) -> list[Holiday]:
    """その年に固有の 1 回限り祝日を返す（2019 即位関連など）。"""
    if year != 2019:
        return []
    # 4/30 と 5/2 は「国民の休日」だが、後の _add_national_holidays でも
    # 同じ結果が出る。先に固定値で入れて名称の安定性を優先する。
    return [
        Holiday(_dt.date(2019, 4, 30), "国民の休日"),
        Holiday(_dt.date(2019, 5, 1), "天皇の即位の日"),
        Holiday(_dt.date(2019, 5, 2), "国民の休日"),
        Holiday(_dt.date(2019, 10, 22), "即位礼正殿の儀の行われる日"),
    ]


def _maybe_append(holidays: list[Holiday], candidate: Holiday | None) -> None:
    """``candidate`` が ``None`` でなければ ``holidays`` に追加するヘルパー。"""
    if candidate is not None:
        holidays.append(candidate)


def _base_holidays_for_year(year: int) -> list[Holiday]:
    """振替・国民の休日を適用する前の「素の」祝日を ``year`` 年について返す。

    2020 年特例と 2019 年 即位関連特例もここで織り込む（後の振替で倒されない）。
    """
    holidays: list[Holiday] = list(_fixed_holidays(year))
    _maybe_append(holidays, _adults_day(year))
    _maybe_append(holidays, _marine_day(year))
    _maybe_append(holidays, _respect_for_the_aged_day(year))
    _maybe_append(holidays, _sports_day(year))
    _maybe_append(holidays, _mountain_day(year))
    _maybe_append(holidays, _emperors_birthday(year))
    holidays.extend(_equinox_holidays(year))
    holidays.extend(_one_off_year_holidays(year))
    return holidays


def _add_substitute_holidays(holidays: list[Holiday], year: int) -> list[Holiday]:
    """2007 年改正以降の振替休日を追加する。

    祝日が日曜なら翌日へ。ただし翌日も祝日なら、さらに先送りして
    「次の非祝日の平日」を振替休日とする。
    """
    if year < 2007:
        return holidays

    result = list(holidays)
    occupied: set[_dt.date] = {h.date for h in result}

    for holiday in sorted(holidays, key=lambda h: h.date):
        if holiday.date.year != year:
            continue
        if holiday.date.weekday() != 6:  # 日曜のみ
            continue
        candidate = holiday.date + _dt.timedelta(days=1)
        while candidate in occupied:
            candidate += _dt.timedelta(days=1)
        # 年内に閉じる
        if candidate.year != year:
            continue
        result.append(Holiday(candidate, "振替休日"))
        occupied.add(candidate)

    return result


def _add_national_holidays(holidays: list[Holiday], year: int) -> list[Holiday]:
    """1985 年以降、2 つの祝日に 1 日挟まれた平日を国民の休日として追加。

    5/4 のサンドイッチ（1985-2006）と、シルバーウィーク（2009- などの 9 月）
    を両方ともこのルールで拾う。
    """
    if year < 1985:
        return holidays

    result = list(holidays)
    occupied: set[_dt.date] = {h.date for h in result if h.date.year == year}

    sorted_dates = sorted(d for d in occupied if d.year == year)
    for first, second in pairwise(sorted_dates):
        gap = (second - first).days
        if gap != 2:
            continue
        sandwiched = first + _dt.timedelta(days=1)
        if sandwiched in occupied:
            continue
        if sandwiched.weekday() >= 5:  # 土日なら国民の休日ではない
            continue
        result.append(Holiday(sandwiched, "国民の休日"))
        occupied.add(sandwiched)

    return result


def _expand_company_holidays(holidays: list[Holiday], year: int) -> list[Holiday]:
    """``COMPANY_HOLIDAYS`` を ``year`` 年について展開する。

    単発・期間・特定年のみ の 3 形式に対応する。期間指定は年跨ぎ（12/29 - 1/3 など）も
    サポートし、両端を ``year`` 年の祝日に登録する。
    """
    result = list(holidays)
    for entry in COMPANY_HOLIDAYS:
        if len(entry) == 3:
            first, second, name = entry
            if isinstance(first, _dt.date):
                # 特定年のみ (_dt.date, _dt.date, name)
                start, end = first, second
                current = max(start, _dt.date(year, 1, 1))
                last = min(end, _dt.date(year, 12, 31))
                while current <= last:
                    result.append(Holiday(current, name))
                    current += _dt.timedelta(days=1)
            else:
                # 単発 (int 月, int 日, name) — 毎年繰り返す
                month = int(first)
                day = int(second)
                result.append(Holiday(_dt.date(year, month, day), name))
        elif len(entry) == 5:
            m1, d1, m2, d2, name = (
                int(entry[0]),
                int(entry[1]),
                int(entry[2]),
                int(entry[3]),
                entry[4],
            )
            if (m1, d1) <= (m2, d2):
                # 同年内
                start = _dt.date(year, m1, d1)
                end = _dt.date(year, m2, d2)
                current = start
                while current <= end:
                    result.append(Holiday(current, name))
                    current += _dt.timedelta(days=1)
            else:
                # 年跨ぎ (例: 12/29 - 1/3)。 ``year`` 年の両端部分の両方を含める。
                cursor = _dt.date(year, m1, d1)
                while cursor <= _dt.date(year, 12, 31):
                    result.append(Holiday(cursor, name))
                    cursor += _dt.timedelta(days=1)
                cursor = _dt.date(year, 1, 1)
                end_in_year = _dt.date(year, m2, d2)
                while cursor <= end_in_year:
                    result.append(Holiday(cursor, name))
                    cursor += _dt.timedelta(days=1)
        else:
            logger.warning(
                "COMPANY_HOLIDAYS のエントリ形式が不明です (3要素または5要素): %r",
                entry,
            )
    return result


# ── 公開クラス ────────────────────────────────────────────────────────────


class ComputedHolidaySource(HolidaySource):
    """計算で祝日の和集合を返すソース。

    ``HolidaySource`` Protocol を実装する。``load()`` で ``Iterable[Holiday]`` を返す。
    ``CabinetOfficeCsvSource`` と並列に置いて、
    ``from_sources([Cabinet, Computed])`` のように和集合で運用する
    （``HolidayCalendar`` 側の先勝ち WARNING ログが衝突をハンドリングする）。

    このソースは **純粋計算のみ** — 外部通信・ファイル読み込みは一切しない。
    社内 BO 環境（オフライン・pip 制限）でもそのまま動く。

    Args:
        from_year: 対象範囲の開始年。省略時は ``DEFAULT_FROM_YEAR`` (1948)。
        to_year: 対象範囲の終了年。省略時は ``DEFAULT_TO_YEAR`` (2099)。
            範囲外でも祝日計算は走るが、春分／秋分の近似精度が下がる旨を
            WARNING ログで知らせる。
    """

    def __init__(
        self,
        *,
        from_year: int | None = None,
        to_year: int | None = None,
    ) -> None:
        self._from_year = from_year if from_year is not None else DEFAULT_FROM_YEAR
        self._to_year = to_year if to_year is not None else DEFAULT_TO_YEAR
        if self._from_year > self._to_year:
            raise ValueError(
                f"from_year ({self._from_year}) が to_year ({self._to_year}) より大きいです。"
            )
        if self._from_year < DEFAULT_FROM_YEAR or self._to_year > DEFAULT_TO_YEAR:
            logger.warning(
                "ComputedHolidaySource の対象範囲 (%d-%d) は高精度範囲 (%d-%d) を"
                "超えています。春分・秋分の近似精度が下がるため、"
                "内閣府 CSV などの確定ソースと併用してください。",
                self._from_year,
                self._to_year,
                DEFAULT_FROM_YEAR,
                DEFAULT_TO_YEAR,
            )

    def load(self) -> list[Holiday]:
        """対象年の範囲について計算した祝日をまとめて返す。

        Returns:
            日付順に並んだ ``Holiday`` のリスト。
        """
        all_holidays: list[Holiday] = []
        for year in range(self._from_year, self._to_year + 1):
            yearly = _base_holidays_for_year(year)
            yearly = _add_substitute_holidays(yearly, year)
            yearly = _add_national_holidays(yearly, year)
            yearly = _expand_company_holidays(yearly, year)
            all_holidays.extend(yearly)

        # 日付順にして返す（同日の重複は呼び出し側で WARNING される前提）
        return sorted(all_holidays, key=lambda h: h.date)


__all__ = ["ComputedHolidaySource", "COMPANY_HOLIDAYS", "DEFAULT_FROM_YEAR", "DEFAULT_TO_YEAR"]
