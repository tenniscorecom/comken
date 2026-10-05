"""comken/core/dates/clock.py — 今の日付・時刻と、月の初日・末日。

タイムゾーンが必要なのは「今の時刻を取るとき」だけ。業務で扱う日付
（CSV・ファイル名・帳票の日付）は「その日」を表すただの日付なので、
datetime.date のまま扱い、タイムゾーンを付けない。
"""

import calendar as _calendar
import datetime


def now() -> datetime.datetime:
    """タイムゾーン付きの現在時刻（この PC のローカル時刻）を返す。"""
    # NOTE: Windows のオフライン環境で追加の tzdata を要求しないよう ZoneInfo は使わない。
    return datetime.datetime.now(datetime.UTC).astimezone()


def today() -> datetime.date:
    """この PC のローカルの今日の日付を返す。"""
    return now().date()


def month_start(target: datetime.date) -> datetime.date:
    """``target`` が属する月の 1日を返す。

    祝日に依存しない純粋な暦計算。営業日計算の前段として
    「その月の最初の営業日を探す」ために使う。
    """
    return target.replace(day=1)


def month_end(target: datetime.date) -> datetime.date:
    """``target`` が属する月の最終日を返す。

    月ごとの日数・閏年を ``calendar.monthrange`` で正しく扱う。
    """
    last_day = _calendar.monthrange(target.year, target.month)[1]
    return target.replace(day=last_day)
